"""Razer BlackWidow Ultimate 2013 — ремаппер макрокнопок без Synapse.

Держит клавиатуру в DRIVER MODE, слушает интерфейс макрокнопок и на нужный
код шлёт действие через Windows SendInput.

Запуск:  uv run --with hidapi python razer_macro_daemon.py
Стоп:    Ctrl+C  (вернёт normal mode + сбросит залипшие модификаторы)

Протокол выяснен по исходникам OpenRazer:
  set/get device mode: class=0x00, id=0x04/0x84, data_size=0x02, args=[mode, 0x00]
  report = 90 байт, transaction_id=0xFF (для PID 0x011A), CRC = XOR байтов [2..87]
  отправка/чтение = HID feature report (report id 0)
"""
import ctypes
import os
import sys
import threading
import time
from ctypes import wintypes

import hid

# Под pythonw (без консоли) sys.stdout=None -> print() падает. Шлём вывод в лог.
if sys.stdout is None or sys.stderr is None:
    _logpath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "razer_macro_daemon.log")
    _logf = open(_logpath, "a", encoding="utf-8", buffering=1)
    sys.stdout = _logf
    sys.stderr = _logf

DEBUG = False  # True -> логировать, что именно впрыскивается в SendInput

# ─────────────────────────── НАСТРОЙКА КНОПОК ───────────────────────────
# Код кнопки (байт[1] репорта) -> действие. Коды: M-кнопки шлют 0x20..0x24.
def MACRO_ACTIONS():
    return {
        0x20: lambda: send_keys("^+{PRINTSCREEN}"),  # M1 -> Ctrl+Shift+PrtScrn
        0x22: lambda: send_keys("{PRINTSCREEN}"),    # M3 -> PrtScrn
        0x24: lambda: send_keys("#+s"),  # -> Win+Shift+S (системная «ножница»)
    }
# ────────────────────────────────────────────────────────────────────────

RAZER_VID = 0x1532
KEYBOARD_PID = 0x011A
TRANSACTION_ID = 0xFF
MODE_NORMAL = 0x00
MODE_DRIVER = 0x03
MACRO_REPORT_TYPE = 0x04  # байт[0] репорта макрокнопок

# ───────────────────────── SendInput (user32) ──────────────────────────
user32 = ctypes.WinDLL("user32", use_last_error=True)
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_SCANCODE = 0x0008

VK = {
    "CTRL": 0x11, "SHIFT": 0x10, "ALT": 0x12, "LWIN": 0x5B,
    "VOLUME_UP": 0xAF, "VOLUME_DOWN": 0xAE, "VOLUME_MUTE": 0xAD,
    "MEDIA_PLAY_PAUSE": 0xB3, "MEDIA_NEXT": 0xB0, "MEDIA_PREV": 0xB1,
    "ENTER": 0x0D, "ESC": 0x1B, "TAB": 0x09, "SPACE": 0x20, "PRINTSCREEN": 0x2C,
    "F13": 0x7C, "F14": 0x7D, "F15": 0x7E, "F16": 0x7F, "F17": 0x80,
    "F18": 0x81, "F19": 0x82, "F20": 0x83, "F21": 0x84, "F22": 0x85,
    "F23": 0x86, "F24": 0x87,
}


ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _INPUTunion(ctypes.Union):
    # ВСЕ члены union обязательны, иначе sizeof(INPUT) неверный и SendInput молчит
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]


INPUT_KEYBOARD = 1
user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT


def _send(inputs):
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    sent = user32.SendInput(n, arr, ctypes.sizeof(INPUT))
    if sent != n:
        err = ctypes.get_last_error()
        print(f"  [SendInput] отправлено {sent}/{n}, GetLastError={err}")
    return sent


def _vk_input(vk, up=False):
    ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, 0)
    return INPUT(INPUT_KEYBOARD, _INPUTunion(ki=ki))


MOD_MAP = {"^": "CTRL", "!": "ALT", "+": "SHIFT", "#": "LWIN"}


def send_keys(spec: str):
    """Мини-парсер в духе AHK: '#+s'=Win+Shift+S, '^c'=Ctrl+C, '{VOLUME_UP}'.
    Модификаторы в начале: ^=Ctrl !=Alt +=Shift #=Win. {NAME} = клавиша из VK."""
    mods, i = [], 0
    while i < len(spec) and spec[i] in MOD_MAP:
        mods.append(MOD_MAP[spec[i]])
        i += 1
    rest, keys, j = spec[i:], [], 0
    while j < len(rest):
        if rest[j] == "{":
            k = rest.index("}", j)
            keys.append(("vk", VK[rest[j + 1:k].upper()]))
            j = k + 1
        else:
            keys.append(("char", rest[j]))
            j += 1
    # резолвим VK заранее: чтобы НЕ нажать модификаторы и упасть на неизвестной клавише
    resolved = []
    for kind, val in keys:
        if kind == "vk":
            resolved.append(val)
        else:
            sc = user32.VkKeyScanW(ord(val))
            resolved.append((sc & 0xFF) if sc != -1 else None)
    if DEBUG:
        print(f"  inject: mods={mods} vks={[hex(v) if v else v for v in resolved]}")
    if mods:
        _send([_vk_input(VK[m]) for m in mods])
    try:
        for vk in resolved:
            if vk is None:
                continue
            _send([_vk_input(vk), _vk_input(vk, up=True)])
    finally:
        if mods:  # модификаторы отпускаем ВСЕГДА, даже при ошибке -> нет залипания
            _send([_vk_input(VK[m], up=True) for m in reversed(mods)])


def _scan_input(scan, up=False, extended=False):
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if extended else 0)
    if up:
        flags |= KEYEVENTF_KEYUP
    ki = KEYBDINPUT(0, scan, flags, 0, 0)
    return INPUT(INPUT_KEYBOARD, _INPUTunion(ki=ki))


def press_printscreen():
    """PrtSc надёжно работает только через scancode (0x37, extended)."""
    _send([_scan_input(0x37, up=False, extended=True),
           _scan_input(0x37, up=True, extended=True)])


def run_cmd(cmd: str):
    import subprocess
    subprocess.Popen(cmd, shell=True)


def flush_stuck_keys():
    """Force-release модификаторов и C — лечит залипание после Ctrl+C-выхода."""
    for vk in (0x43, 0x11, 0xA2, 0xA3, 0x10, 0xA0, 0xA1, 0x12, 0xA4, 0xA5, 0x5B, 0x5C):
        try:
            _send([_vk_input(vk, up=True)])
        except Exception:
            pass


# ───────────────────────── Razer protocol ──────────────────────────────
def build_report(command_class, command_id, data_size, args):
    r = bytearray(90)
    r[1] = TRANSACTION_ID
    r[5] = data_size
    r[6] = command_class
    r[7] = command_id
    for i, b in enumerate(args):
        r[8 + i] = b
    crc = 0
    for i in range(2, 88):
        crc ^= r[i]
    r[88] = crc
    return bytes(r)


def set_device_mode(dev, mode):
    dev.send_feature_report(b"\x00" + build_report(0x00, 0x04, 0x02, [mode, 0x00]))


def get_device_mode(dev):
    """Прочитать текущий режим обратно. Возвращает байт mode или None."""
    try:
        dev.send_feature_report(b"\x00" + build_report(0x00, 0x84, 0x02, [0x00, 0x00]))
        time.sleep(0.02)
        resp = dev.get_feature_report(0x00, 91)
        if resp and len(resp) >= 10:
            return resp[9]  # report id(1) + report index 8 (arguments[0]) = resp[9]
    except Exception:
        pass
    return None


def enum_keyboard():
    return [d for d in hid.enumerate()
            if d["vendor_id"] == RAZER_VID and d["product_id"] == KEYBOARD_PID]


def ensure_single_instance():
    """Не дать запуститься второму демону (named mutex)."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW(None, False, "RazerMacroDaemon_singleton")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        print("Демон уже запущен — выходим.")
        sys.exit(0)


def setup_devices():
    """Открыть интерфейсы, включить driver mode, найти control + macro-интерфейс.
    Возвращает (handles, control, read_list) либо завершает процесс при ошибке."""
    descs = enum_keyboard()
    if not descs:
        print("Клавиатура Razer 0x011A не найдена. Подключена? Synapse закрыт?")
        sys.exit(1)

    handles = []  # (label, desc, dev)
    macro_dev = None
    for d in descs:
        label = f"MI_{d['interface_number']:02d}/up={hex(d['usage_page'])}/u={hex(d['usage'])}"
        if b"Col" in d["path"]:
            label += "/Col" + d["path"].decode(errors="replace").split("Col")[-1][:2]
        try:
            dev = hid.device()
            dev.open_path(d["path"])
            dev.set_nonblocking(True)
            handles.append((label, d, dev))
            if d["usage_page"] == 0x1 and d["usage"] == 0x0 and b"Col04" in d["path"]:
                macro_dev = (label, dev)
        except Exception as e:
            print(f"[SKIP] {label}: {e}")

    if not handles:
        print("Не удалось открыть ни один интерфейс.")
        sys.exit(1)

    # авто-определение целевого control-интерфейса: выставить driver mode и прочитать обратно
    control = []
    for label, d, dev in handles:
        try:
            set_device_mode(dev, MODE_DRIVER)
            if get_device_mode(dev) == MODE_DRIVER:
                control.append((label, dev))
        except Exception:
            pass
    if control:
        print("Целевой control-интерфейс:", ", ".join(l for l, _ in control))
    else:
        print("Не удалось верифицировать режим, шлю на все интерфейсы (fallback).")
        control = [(l, dev) for l, _, dev in handles]
        for _, dev in control:
            try:
                set_device_mode(dev, MODE_DRIVER)
            except Exception:
                pass

    if not macro_dev:
        print("Не найден интерфейс макрокнопок (Col04) — читаю со всех.")
        read_list = [(l, dev) for l, _, dev in handles]
    else:
        print("Интерфейс макрокнопок:", macro_dev[0])
        read_list = [macro_dev]
    return handles, control, read_list


def run_hid_loop(actions, control, handles, read_list, stop_event):
    """HID-цикл (фоновый поток): читает макрокнопки, шлёт действия.
    Перед выходом возвращает normal mode и сбрасывает залипшие клавиши."""
    stopfile = os.path.join(os.path.dirname(os.path.abspath(__file__)), "STOP")
    if os.path.exists(stopfile):
        try:
            os.remove(stopfile)
        except OSError:
            pass

    last = 0x00
    try:
        while not stop_event.is_set():
            if os.path.exists(stopfile):  # внешняя остановка через stop.cmd
                try:
                    os.remove(stopfile)
                except OSError:
                    pass
                print("Получен STOP — выходим.")
                stop_event.set()
                break
            for _, dev in read_list:
                try:
                    data = dev.read(64)
                except Exception:
                    data = None
                if data and data[0] == MACRO_REPORT_TYPE:
                    code = data[1]
                    if code != 0x00 and code != last:  # фронт нажатия
                        action = actions.get(code)
                        print(f"M-key {hex(code)} -> {'выполняю' if action else 'не назначено'}")
                        if action:
                            try:
                                action()
                            except Exception as e:
                                print(f"  ошибка действия: {e}")
                    last = code
            time.sleep(0.003)
    finally:
        time.sleep(0.05)
        for _, dev in control:
            try:
                set_device_mode(dev, MODE_NORMAL)
            except Exception:
                pass
        time.sleep(0.05)
        flush_stuck_keys()
        for _, _, dev in handles:
            try:
                dev.close()
            except Exception:
                pass
        print("Normal mode восстановлен, клавиши сброшены. Пока.")


def make_tray_image():
    """Простая иконка для трея: тёмный круг с зелёной 'Rz'."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    green = (60, 200, 90, 255)
    d.ellipse((3, 3, 61, 61), fill=(25, 25, 28, 255), outline=green, width=4)
    d.text((17, 20), "Rz", fill=green)
    return img


def main():
    ensure_single_instance()
    actions = MACRO_ACTIONS()
    handles, control, read_list = setup_devices()

    binds = ", ".join(hex(k) for k in actions)
    print("Демон запущен. Биндинги:", binds)

    stop_event = threading.Event()
    worker = threading.Thread(
        target=run_hid_loop,
        args=(actions, control, handles, read_list, stop_event),
        daemon=True,
    )
    worker.start()

    # трей-иконка (основной поток). Если pystray нет — крутимся headless.
    try:
        import pystray
    except ImportError:
        print("pystray не установлен — работаю без трея (Ctrl+C / stop.cmd).")
        try:
            while not stop_event.is_set():
                time.sleep(0.2)
        except KeyboardInterrupt:
            stop_event.set()
        worker.join(timeout=3)
        return

    def on_quit(icon, _item=None):
        stop_event.set()
        worker.join(timeout=3)
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Razer Macro — M5 → Win+Shift+S", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Выход", on_quit),
    )
    icon = pystray.Icon("razer_macro", make_tray_image(), "Razer Macro Daemon", menu)
    icon.run()  # блокирует, пока не «Выход»


if __name__ == "__main__":
    main()
