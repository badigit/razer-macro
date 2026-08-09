"""Протокол Razer, driver mode и цикл обработки макрокнопок."""
import ctypes
import threading
import time

from . import hidwin, keys

TRANSACTION_ID = 0xFF
MODE_NORMAL = 0x00
MODE_DRIVER = 0x03
MACRO_REPORT_TYPE = 0x04  # байт[0] репорта макрокнопок

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def build_report(command_class, command_id, data_size, args):
    """Razer HID report: 90 байт, CRC = XOR байтов [2..87]."""
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
    dev.send_feature(b"\x00" + build_report(0x00, 0x04, 0x02, [mode, 0x00]))


def get_device_mode(dev):
    """Прочитать режим обратно; None, если интерфейс не отвечает."""
    try:
        dev.send_feature(b"\x00" + build_report(0x00, 0x84, 0x02, [0x00, 0x00]))
        time.sleep(0.02)
        resp = dev.get_feature(0)
        if resp and len(resp) >= 10:
            return resp[9]  # report id(1) + arguments[0] по смещению 8
    except OSError:
        pass
    return None


def describe(info):
    label = f"MI_{info['mi']:02d}" if info["mi"] is not None else "MI_??"
    low = info["path"].lower()
    if "&col" in low:
        label += "/Col" + low.split("&col")[1][:2]
    return f"{label} up={hex(info['usage_page'])} u={hex(info['usage'])}"


class DeviceNotFound(RuntimeError):
    pass


class MacroDaemon:
    """Держит клавиатуру в driver mode и превращает M-кнопки в действия."""

    def __init__(self, config, log=print, debug=False):
        self.config = config
        self.log = log
        self.debug = debug
        self.devices = []      # все открытые интерфейсы
        self.control = []      # те, что приняли driver mode
        self.readers = []      # интерфейсы макрокнопок
        self._stop = threading.Event()
        self._stop_event_handle = kernel32.CreateEventW(None, True, False, None)
        self._lock = threading.Lock()

    # ── подключение ──
    def open(self):
        infos = hidwin.enumerate_devices(self.config.vendor_id, self.config.product_id)
        if not infos:
            raise DeviceNotFound(
                f"Клавиатура {self.config.vendor_id:#06x}:{self.config.product_id:#06x} "
                "не найдена. Подключена? Synapse закрыт?")

        for info in infos:
            try:
                self.devices.append(hidwin.HidDevice(info))
            except OSError as e:
                self.log(f"[skip] {describe(info)}: {e}")
        if not self.devices:
            raise DeviceNotFound("Не удалось открыть ни один интерфейс.")

        # control-интерфейс определяем фактом: ставим режим и читаем обратно
        for dev in self.devices:
            if not dev.info["feature_len"]:
                continue  # интерфейс без feature-репортов командой не управляется
            try:
                set_device_mode(dev, MODE_DRIVER)
                if get_device_mode(dev) == MODE_DRIVER:
                    self.control.append(dev)
            except OSError:
                pass
        if self.control:
            self.log("Control-интерфейс: "
                     + ", ".join(describe(d.info) for d in self.control))
        else:
            self.log("Режим не подтвердился — шлю на все интерфейсы (fallback).")
            self.control = list(self.devices)
            for dev in self.control:
                try:
                    set_device_mode(dev, MODE_DRIVER)
                except OSError:
                    pass

        # макрокнопки: отдельная коллекция (Col04), читаемая и не занятая системой
        self.readers = [d for d in self.devices
                        if d.readable and "&col04" in d.path.lower()]
        if not self.readers:
            self.readers = [d for d in self.devices if d.readable]
            self.log("Коллекция Col04 не найдена — читаю все доступные интерфейсы.")
        else:
            self.log("Макрокнопки: "
                     + ", ".join(describe(d.info) for d in self.readers))

        # интерфейсы, которые не нужны ни для команд, ни для чтения, держать
        # открытыми незачем — освобождаем хендлы и заодно не мешаем другим
        keep = {id(d) for d in self.control} | {id(d) for d in self.readers}
        for dev in [d for d in self.devices if id(d) not in keep]:
            dev.close()
            self.devices.remove(dev)

    # ── цикл ──
    def run(self):
        """Блокирует до stop(). Ждёт события устройства, а не крутит поллинг."""
        pressed = set()
        handles = [d.event for d in self.readers] + [self._stop_event_handle]
        try:
            while not self._stop.is_set():
                for dev in self.readers:
                    dev.start_read()
                idx = hidwin.wait_any(handles, 1000)
                if idx is None:
                    continue                      # таймаут — просто новый круг
                if idx == len(handles) - 1:
                    break                         # событие остановки
                data = self.readers[idx].complete_read()
                if data:
                    pressed = self._handle(data, pressed)
        finally:
            self.shutdown()

    def _handle(self, data, pressed):
        """Репорт содержит ВСЕ удерживаемые коды, поэтому смотрим разницу наборов."""
        if not data or data[0] != MACRO_REPORT_TYPE:
            return pressed
        now = {b for b in data[1:] if b}
        for code in now - pressed:
            self.fire(code)
        return now

    def fire(self, code):
        bind = self.config.binds.get(code)
        if not bind:
            self.log(f"M-key {code:#04x} -> не назначено")
            return
        kind, value = bind
        self.log(f"M-key {code:#04x} -> {value}")
        try:
            if kind == "run":
                keys.run_command(value)
            else:
                keys.send_keys(value, log=self.log, debug=self.debug)
        except Exception as e:
            self.log(f"  ошибка действия: {e}")

    def reload_config(self, config):
        with self._lock:
            self.config = config

    def stop(self):
        self._stop.set()
        kernel32.SetEvent(self._stop_event_handle)

    def shutdown(self):
        """Вернуть normal mode и отпустить всё — иначе клавиатура останется немой."""
        time.sleep(0.05)
        for dev in self.control:
            try:
                set_device_mode(dev, MODE_NORMAL)
            except OSError:
                pass
        time.sleep(0.05)
        keys.flush_stuck_keys()
        for dev in self.devices:
            try:
                dev.close()
            except OSError:
                pass
        self.devices, self.control, self.readers = [], [], []
        self.log("Normal mode восстановлен, клавиши сброшены.")
