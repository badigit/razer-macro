"""Загрузка config.toml: бинды, устройство, поведение."""
import os
import sys
import tomllib

APP_NAME = "razer-macro"

# Коды растут сверху вниз, а маркировка M1..M5 на клавиатуре идёт снизу вверх:
# верхняя кнопка (M5) шлёт 0x20, нижняя (M1) — 0x24.
MACRO_CODES = {f"M{n}": 0x25 - n for n in range(1, 6)}

DEFAULT_CONFIG = """\
# Razer Macro — конфигурация. После правки: меню в трее -> «Перечитать конфиг».

[keyboard]
# BlackWidow Ultimate 2013. Свою модель можно найти так:
#   razer-macro.exe --list
vendor_id = "0x1532"
product_id = "0x011A"

[binds]
# Кнопки маркированы снизу вверх: M1 — нижняя, M5 — верхняя.
# Значение — комбинация клавиш: ^=Ctrl !=Alt +=Shift #=Win, {NAME} — из списка
# именованных клавиш ({PRINTSCREEN}, {F13}, {VOLUME_UP}, ...).
M1 = "^+{PRINTSCREEN}"
M3 = "{PRINTSCREEN}"
M5 = "#+s"

# Запуск программы вместо клавиш — префикс run:
# M4 = "run:notepad.exe"

# Вместо имени можно указать сырой код кнопки:
# 0x21 = "{VOLUME_UP}"
"""


def app_dir():
    """Папка, рядом с которой лежит конфиг: где exe, либо корень репозитория."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def config_path(explicit=None):
    """Конфиг ищем рядом с exe, затем в %LOCALAPPDATA%\\razer-macro."""
    if explicit:
        return os.path.abspath(explicit)
    local = os.path.join(app_dir(), "config.toml")
    if os.path.exists(local):
        return local
    roaming = os.path.join(data_dir(), "config.toml")
    if os.path.exists(roaming):
        return roaming
    # ничего нет — создадим рядом с exe, а если туда нельзя, то в LOCALAPPDATA
    try:
        with open(local, "x", encoding="utf-8") as f:
            f.write(DEFAULT_CONFIG)
        return local
    except OSError:
        with open(roaming, "w", encoding="utf-8") as f:
            f.write(DEFAULT_CONFIG)
        return roaming


def _as_int(value, what):
    if isinstance(value, int):
        return value
    try:
        return int(str(value), 0)
    except ValueError:
        raise ValueError(f"{what}: ожидалось число, получено {value!r}")


def resolve_code(key):
    """'M1' или '0x24' -> код кнопки."""
    name = str(key).strip().upper()
    if name in MACRO_CODES:
        return MACRO_CODES[name]
    return _as_int(key, f"код кнопки {key!r}")


class Config:
    def __init__(self, path, vendor_id, product_id, binds, raw_binds):
        self.path = path
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.binds = binds          # {код: (вид, значение)}
        self.raw_binds = raw_binds  # {исходный ключ: строка} — для меню трея


def load(explicit=None):
    path = config_path(explicit)
    with open(path, "rb") as f:
        data = tomllib.load(f)

    kb = data.get("keyboard", {})
    vendor_id = _as_int(kb.get("vendor_id", "0x1532"), "keyboard.vendor_id")
    product_id = _as_int(kb.get("product_id", "0x011A"), "keyboard.product_id")

    binds, raw = {}, {}
    for key, value in (data.get("binds") or {}).items():
        code = resolve_code(key)
        text = str(value).strip()
        if text.lower().startswith("run:"):
            binds[code] = ("run", text[4:].strip())
        else:
            binds[code] = ("keys", text)
        raw[key] = text
    return Config(path, vendor_id, product_id, binds, raw)
