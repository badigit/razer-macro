"""Впрыск нажатий через SendInput и мини-парсер спецификаций клавиш."""
import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
INPUT_KEYBOARD = 1

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

VK = {
    "CTRL": 0x11, "SHIFT": 0x10, "ALT": 0x12, "LWIN": 0x5B, "RWIN": 0x5C,
    "VOLUME_UP": 0xAF, "VOLUME_DOWN": 0xAE, "VOLUME_MUTE": 0xAD,
    "MEDIA_PLAY_PAUSE": 0xB3, "MEDIA_NEXT": 0xB0, "MEDIA_PREV": 0xB1,
    "MEDIA_STOP": 0xB2,
    "ENTER": 0x0D, "ESC": 0x1B, "TAB": 0x09, "SPACE": 0x20, "BACKSPACE": 0x08,
    "PRINTSCREEN": 0x2C, "INSERT": 0x2D, "DELETE": 0x2E,
    "HOME": 0x24, "END": 0x23, "PAGEUP": 0x21, "PAGEDOWN": 0x22,
    "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
    "CAPSLOCK": 0x14, "NUMLOCK": 0x90, "SCROLLLOCK": 0x91, "PAUSE": 0x13,
    "APPS": 0x5D,
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73, "F5": 0x74, "F6": 0x75,
    "F7": 0x76, "F8": 0x77, "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "F13": 0x7C, "F14": 0x7D, "F15": 0x7E, "F16": 0x7F, "F17": 0x80,
    "F18": 0x81, "F19": 0x82, "F20": 0x83, "F21": 0x84, "F22": 0x85,
    "F23": 0x86, "F24": 0x87,
}

# Клавиши расширенного набора: в железе идут с префиксом E0. Часть приёмников
# хоткеев сверяет флаг KEYEVENTF_EXTENDEDKEY и без него нажатие игнорирует —
# на этом спотыкался Ctrl+Shift+PrtScrn.
EXTENDED_VKS = {
    0x2C, 0x2D, 0x2E, 0x24, 0x23, 0x21, 0x22,
    0x25, 0x26, 0x27, 0x28, 0x5B, 0x5C, 0x90, 0x6F,
}

MOD_MAP = {"^": "CTRL", "!": "ALT", "+": "SHIFT", "#": "LWIN"}


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
    # ВСЕ члены union обязательны, иначе sizeof(INPUT) мал и SendInput молча
    # отказывает — на этом теряли час.
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT


def _send(inputs, log=None):
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    sent = user32.SendInput(n, arr, ctypes.sizeof(INPUT))
    if sent != n and log:
        log(f"  [SendInput] отправлено {sent}/{n}, GetLastError={ctypes.get_last_error()}")
    return sent


def _vk_input(vk, up=False):
    flags = KEYEVENTF_KEYUP if up else 0
    if vk in EXTENDED_VKS:
        flags |= KEYEVENTF_EXTENDEDKEY
    return INPUT(INPUT_KEYBOARD, _INPUTunion(ki=KEYBDINPUT(vk, 0, flags, 0, 0)))


class UnknownKey(ValueError):
    pass


def parse_spec(spec: str):
    """'^+{PRINTSCREEN}' -> (['CTRL','SHIFT'], [0x2C]). Валидирует на этапе разбора.

    Модификаторы в начале: ^=Ctrl !=Alt +=Shift #=Win. {NAME} — клавиша из VK,
    остальные символы резолвятся через раскладку (VkKeyScanW).
    """
    mods, i = [], 0
    while i < len(spec) and spec[i] in MOD_MAP:
        mods.append(MOD_MAP[spec[i]])
        i += 1
    rest, vks, j = spec[i:], [], 0
    while j < len(rest):
        if rest[j] == "{":
            end = rest.find("}", j)
            if end == -1:
                raise UnknownKey(f"незакрытая скобка в {spec!r}")
            name = rest[j + 1:end].upper()
            if name not in VK:
                raise UnknownKey(f"неизвестная клавиша {{{name}}} в {spec!r}")
            vks.append(VK[name])
            j = end + 1
        else:
            sc = user32.VkKeyScanW(ord(rest[j]))
            if sc == -1:
                raise UnknownKey(f"символ {rest[j]!r} не набирается в текущей раскладке")
            vks.append(sc & 0xFF)
            j += 1
    if not vks and not mods:
        raise UnknownKey(f"пустая комбинация {spec!r}")
    return mods, vks


def send_keys(spec: str, log=None, debug=False):
    mods, vks = parse_spec(spec)
    if debug and log:
        log(f"  inject: mods={mods} vks={[hex(v) for v in vks]}")
    if mods:
        _send([_vk_input(VK[m]) for m in mods], log)
    try:
        for vk in vks:
            _send([_vk_input(vk), _vk_input(vk, up=True)], log)
    finally:
        # модификаторы отпускаем ВСЕГДА, даже при ошибке — иначе залипнет Win
        # и обычные нажатия превратятся в Win+клавиша
        if mods:
            _send([_vk_input(VK[m], up=True) for m in reversed(mods)], log)


def flush_stuck_keys():
    """Force-release модификаторов — лечит залипание после аварийного выхода."""
    for vk in (0x43, 0x11, 0xA2, 0xA3, 0x10, 0xA0, 0xA1, 0x12, 0xA4, 0xA5, 0x5B, 0x5C):
        try:
            _send([_vk_input(vk, up=True)])
        except Exception:
            pass


def run_command(cmd: str):
    import subprocess
    subprocess.Popen(cmd, shell=True)
