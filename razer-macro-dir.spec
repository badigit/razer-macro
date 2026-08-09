# Сборка «папкой»: один процесс вместо двух и старт без распаковки во временный
# каталог. Именно этот вариант экономнее по памяти.
#   python -m PyInstaller --clean --noconfirm razer-macro-dir.spec

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
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="razer-macro",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="razer-macro",
)
