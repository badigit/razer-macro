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
user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
user32.MapVirtualKeyW.restype = wintypes.UINT

MAPVK_VK_TO_VSC = 0


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
    # сканкод в событии: у физического нажатия он всегда есть, и часть
    # приёмников (хуки, игры) событие без сканкода игнорирует
    scan = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
    return INPUT(INPUT_KEYBOARD, _INPUTunion(ki=KEYBDINPUT(vk, scan, flags, 0, 0)))


class UnknownKey(ValueError):
    pass


# VK физических клавиш для знаков, у которых код не выводится из ord(символа)
# (клавиши OEM-блока US-раскладки)
_OEM_VK = {
    " ": 0x20, "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC,
    ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
}
# Shift-варианты тех же клавиш: хоткей — про клавишу, а не про символ
_OEM_SHIFTED = {
    "~": "`", "_": "-", "+": "=", "{": "[", "}": "]", "|": "\\", ":": ";",
    '"': "'", "<": ",", ">": ".", "?": "/",
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7",
    "*": "8", "(": "9", ")": "0",
}
# ЙЦУКЕН: буква -> латинская буква на той же физической клавише. Бинды с
# кириллицей тоже не зависят от активной раскладки («й» жмёт клавишу Q и т.д.)
_CYRILLIC_TO_US = {
    "ё": "`", "й": "q", "ц": "w", "у": "e", "к": "r", "е": "t", "н": "y",
    "г": "u", "ш": "i", "щ": "o", "з": "p", "х": "[", "ъ": "]",
    "ф": "a", "ы": "s", "в": "d", "а": "f", "п": "g", "р": "h", "о": "j",
    "л": "k", "д": "l", "ж": ";", "э": "'",
    "я": "z", "ч": "x", "с": "c", "м": "v", "и": "b", "т": "n", "ь": "m",
    "б": ",", "ю": ".",
}


def _char_vk(ch):
    """VK физической клавиши по символу — без участия активной раскладки.

    Латиница, цифры, знаки US-раскладки и кириллица (через ЙЦУКЕН) резолвятся
    по позиции клавиши, поэтому хоткей срабатывает при любой раскладке.
    VkKeyScanW остаётся для символов вне обеих таблиц (например, украинских) —
    те зависят от раскладки.
    """
    c = ch.lower()
    if "a" <= c <= "z":
        return 0x41 + ord(c) - ord("a")
    if "0" <= c <= "9":
        return ord(c)
    if c in _OEM_VK:
        return _OEM_VK[c]
    if c in _OEM_SHIFTED:
        return _char_vk(_OEM_SHIFTED[c])
    if c in _CYRILLIC_TO_US:
        return _char_vk(_CYRILLIC_TO_US[c])
    sc = user32.VkKeyScanW(ord(ch))
    if sc == -1:
        raise UnknownKey(f"символ {ch!r} не набирается в текущей раскладке")
    return sc & 0xFF


def parse_spec(spec: str):
    """'^+{PRINTSCREEN}' -> (['CTRL','SHIFT'], [0x2C]). Валидирует на этапе разбора.

    Модификаторы в начале: ^=Ctrl !=Alt +=Shift #=Win. {NAME} — клавиша из VK.
    Латиница, цифры, знаки и кириллица (через ЙЦУКЕН) резолвятся в физическую
    клавишу — независимо от активной раскладки; остальное — через VkKeyScanW.
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
            vks.append(_char_vk(rest[j]))
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
