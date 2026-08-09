"""Запуск из исходников и точка входа для PyInstaller."""
import sys

if __name__ == "__main__":
    from razer_macro.__main__ import main, crash_guard

    with crash_guard():
        sys.exit(main())
