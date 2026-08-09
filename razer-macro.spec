# PyInstaller: один exe без консоли, без сторонних зависимостей.
# Сборка:  python -m PyInstaller --clean --noconfirm razer-macro.spec

block_cipher = None

# Проект работает на stdlib + ctypes, поэтому половину стандартной библиотеки
# можно не тащить: меньше файл, быстрее старт, меньше страниц в памяти.
EXCLUDES = [
    "tkinter", "unittest", "pydoc", "doctest", "test", "lib2to3", "sqlite3",
    "asyncio", "multiprocessing", "concurrent", "email", "html", "http",
    "xml", "xmlrpc", "urllib.request", "ssl", "hashlib", "bz2", "lzma",
    "curses", "distutils", "setuptools", "pip", "numpy", "PIL", "pystray",
]

a = Analysis(
    ["razer-macro.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="razer-macro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX сильно повышает шанс ложного срабатывания антивирусов
    runtime_tmpdir=None,
    console=False,      # трей-утилита, консоль не нужна
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
