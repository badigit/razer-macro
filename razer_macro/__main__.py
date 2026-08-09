"""Точка входа: трей, автозапуск, диагностика."""
import argparse
import contextlib
import ctypes
import gc
import os
import subprocess
import sys
import threading

from . import autostart, config as cfg, daemon as dmn, hidwin, tray

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

MUTEX_NAME = "RazerMacroDaemon_singleton"
ERROR_ALREADY_EXISTS = 183
MB_ICONERROR = 0x10
MB_ICONINFORMATION = 0x40
TIMER_TRIM = 1
TRIM_PERIOD_MS = 5 * 60 * 1000


@contextlib.contextmanager
def crash_guard():
    """Любое падение — в лог и в окно с ошибкой, а не в тишину."""
    try:
        yield
    except SystemExit:
        raise
    except BaseException:
        import traceback
        text = traceback.format_exc()
        try:
            with open(os.path.join(cfg.data_dir(), "daemon.log"), "a",
                      encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError:
            pass
        message_box(f"Razer Macro упал:\n\n{text[-800:]}", flags=MB_ICONERROR)
        raise


def fix_console_encoding():
    """Согласовать вывод с кодовой страницей консоли (у нас обычно cp866).

    Меняем кодировку своего потока, а не CP консоли: SetConsoleOutputCP пережил
    бы выход процесса и сломал вывод соседним программам.
    """
    # У windowed-сборки своей консоли нет и GetConsoleOutputCP вернёт 0: вывод
    # уходит в pipe, который на той стороне читают в OEM-кодировке (у нас cp866).
    cp = kernel32.GetConsoleOutputCP() or kernel32.GetOEMCP()
    if not cp:
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding=f"cp{cp}", errors="replace")
        except (AttributeError, LookupError, ValueError, OSError):
            pass


def ensure_streams(log_path):
    """Под pythonw sys.stdout/stderr = None.

    Это не косметика: когда ctypes печатает traceback из оконного колбэка, а
    stderr нет, процесс умирает молча, без единой записи. Подставляем файл.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return None
    try:
        stream = open(log_path, "a", encoding="utf-8", buffering=1)
    except OSError:
        stream = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
    return stream


def trim_working_set():
    """Отдать системе страницы, которые процессу больше не нужны.

    Демон 99% времени спит на событии; без этого интерпретатор так и держит
    пик, набранный при старте. Данные не теряются — то, что понадобится,
    вернётся из страничного файла.
    """
    kernel32.SetProcessWorkingSetSize(kernel32.GetCurrentProcess(), -1, -1)


class Logger:
    """Лог в файл с обрезкой: демон живёт месяцами, файл расти не должен."""

    LIMIT = 256 * 1024

    def __init__(self, path, echo=False):
        self.path = path
        self.echo = echo
        self._lock = threading.Lock()
        try:
            if os.path.exists(path) and os.path.getsize(path) > self.LIMIT:
                with open(path, "rb") as f:
                    f.seek(-self.LIMIT // 2, os.SEEK_END)
                    tail = f.read()
                with open(path, "wb") as f:
                    f.write(tail)
        except OSError:
            pass

    def __call__(self, message):
        if self.echo:
            try:
                print(message, flush=True)
            except (OSError, ValueError):
                pass
        with self._lock:
            try:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(f"{message}\n")
            except OSError:
                pass


def message_box(text, title="Razer Macro", flags=MB_ICONINFORMATION):
    user32.MessageBoxW(None, text, title, flags)


def single_instance():
    kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS


def cmd_list():
    """Показать HID-интерфейсы — чтобы найти VID/PID своей модели."""
    devices = hidwin.enumerate_devices()
    razer = [d for d in devices if d["vendor_id"] == 0x1532]
    rows = razer or devices
    if razer:
        print("Устройства Razer:")
    else:
        print("Устройств Razer не найдено, показываю все HID-интерфейсы:")
    for d in rows:
        print(f"  {d['vendor_id']:#06x}:{d['product_id']:#06x}  {dmn.describe(d)}"
              f"  feature={d['feature_len']}")
    return 0


def build_menu(conf, on_reload, on_edit):
    items = [(f"Конфиг: {os.path.basename(conf.path)}", None)]
    for name, spec in conf.raw_binds.items():
        code = cfg.resolve_code(name)
        items.append((f"{name} ({code:#04x}) → {spec}", None))
    items.append(("-", None))
    items.append(("Открыть конфиг", on_edit))
    items.append(("Перечитать конфиг", on_reload))
    return items


def run_tray(conf, log, debug, console):
    macro = dmn.MacroDaemon(conf, log=log, debug=debug)
    try:
        macro.open()
    except dmn.DeviceNotFound as e:
        log(str(e))
        if not console:
            message_box(str(e), flags=MB_ICONERROR)
        return 1

    log("Демон запущен. Биндинги: "
        + ", ".join(f"{c:#04x}" for c in conf.binds) or "(пусто)")

    worker = threading.Thread(target=macro.run, name="hid", daemon=True)
    worker.start()

    state = {"conf": conf}

    def on_reload():
        try:
            fresh = cfg.load(state["conf"].path)
        except Exception as e:
            message_box(f"Конфиг не прочитан:\n{e}", flags=MB_ICONERROR)
            return
        state["conf"] = fresh
        macro.reload_config(fresh)
        icon.set_items(build_menu(fresh, on_reload, on_edit))
        icon.set_tooltip(tooltip_for(fresh))
        log(f"Конфиг перечитан: {len(fresh.binds)} биндов")

    def on_edit():
        subprocess.Popen(["notepad.exe", state["conf"].path])

    def on_quit():
        macro.stop()
        worker.join(timeout=3)

    icon = tray.Tray(tooltip_for(conf), build_menu(conf, on_reload, on_edit), on_quit)
    icon.add_timer(TIMER_TRIM, TRIM_PERIOD_MS, trim_working_set)

    gc.collect()
    gc.freeze()  # объекты старта в постоянную генерацию: меньше работы сборщику
    trim_working_set()

    icon.run()  # блокирует до «Выход»
    return 0


def tooltip_for(conf):
    binds = ", ".join(f"{name}→{spec}" for name, spec in conf.raw_binds.items())
    return f"Razer Macro — {binds}" if binds else "Razer Macro"


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="razer-macro",
        description="Макрокнопки Razer без Synapse: M-кнопки -> комбинации клавиш.")
    parser.add_argument("--install", action="store_true",
                        help="прописать автозапуск при входе в систему")
    parser.add_argument("--uninstall", action="store_true",
                        help="убрать автозапуск")
    parser.add_argument("--status", action="store_true",
                        help="показать состояние автозапуска и путь конфига")
    parser.add_argument("--list", action="store_true",
                        help="перечислить HID-устройства (поиск своего VID/PID)")
    parser.add_argument("--config", metavar="PATH", help="путь к config.toml")
    parser.add_argument("--console", action="store_true",
                        help="дублировать лог в консоль")
    parser.add_argument("--debug", action="store_true",
                        help="логировать, что именно уходит в SendInput")
    args = parser.parse_args(argv)

    if ensure_streams(os.path.join(cfg.data_dir(), "daemon.log")) is None:
        fix_console_encoding()

    if args.list:
        return cmd_list()

    if args.install:
        print(f"Автозапуск включён:\n  {autostart.install()}")
        return 0
    if args.uninstall:
        print("Автозапуск выключен." if autostart.uninstall() else "Автозапуска и не было.")
        return 0
    if args.status:
        current = autostart.status()
        print(f"Автозапуск: {current or 'выключен'}")
        print(f"Конфиг:     {cfg.config_path(args.config)}")
        print(f"Лог:        {os.path.join(cfg.data_dir(), 'daemon.log')}")
        return 0

    log = Logger(os.path.join(cfg.data_dir(), "daemon.log"),
                 echo=args.console and sys.stdout is not None)

    if not single_instance():
        log("Демон уже запущен — выходим.")
        return 0

    try:
        conf = cfg.load(args.config)
    except Exception as e:
        text = f"Конфиг не прочитан:\n{e}"
        log(text)
        message_box(text, flags=MB_ICONERROR)
        return 1

    return run_tray(conf, log, args.debug, args.console)


if __name__ == "__main__":
    sys.exit(main())
