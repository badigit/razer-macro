"""Автозапуск через HKCU\\...\\Run — без прав администратора и без VBS-обёрток."""
import os
import sys
import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "RazerMacro"


def _command():
    """Команда запуска текущей сборки: exe напрямую либо pythonw + скрипт."""
    if getattr(sys, "frozen", False):
        return f'"{os.path.abspath(sys.executable)}"'
    exe = sys.executable
    # обычный python.exe открыл бы консоль при каждом входе в систему
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pythonw):
        exe = pythonw
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "razer-macro.py")
    return f'"{exe}" "{script}"'


def install():
    cmd = _command()
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, cmd)
    return cmd


def uninstall():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
        return True
    except FileNotFoundError:
        return False


def status():
    """Текущее значение автозапуска или None."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_QUERY_VALUE) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return value
    except FileNotFoundError:
        return None
