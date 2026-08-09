"""Иконка в трее на голом ctypes: Shell_NotifyIcon + message-only окно.

Замена pystray, который тянет за собой Pillow. Иконка рисуется прямо в память
(круг с зелёной обводкой), поэтому ни картинок в комплекте, ни зависимостей.
"""
import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_DESTROY = 0x0002
WM_COMMAND = 0x0111
WM_TIMER = 0x0113
WM_RBUTTONUP = 0x0205
WM_LBUTTONDBLCLK = 0x0203
WM_APP = 0x8000
WM_TRAYICON = WM_APP + 1
WM_CLOSE = 0x0010

NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIF_MESSAGE = 0x01
NIF_ICON = 0x02
NIF_TIP = 0x04

MF_STRING = 0x0000
MF_SEPARATOR = 0x0800
MF_GRAYED = 0x0001
MF_CHECKED = 0x0008
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100

HWND_MESSAGE = wintypes.HWND(-3)
IDC_ARROW = 32512

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD),
                ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
                ("uVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64),
                ("dwInfoFlags", wintypes.DWORD)]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD),
                ("yHotspot", wintypes.DWORD), ("hbmMask", wintypes.HBITMAP),
                ("hbmColor", wintypes.HBITMAP)]


user32.DefWindowProcW.restype = ctypes.c_longlong
user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                  wintypes.LPARAM)
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = (wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                   wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                   wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p)
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.TrackPopupMenu.restype = wintypes.BOOL
user32.TrackPopupMenu.argtypes = (wintypes.HMENU, wintypes.UINT, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                  ctypes.c_void_p)
shell32.Shell_NotifyIconW.argtypes = (wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW))
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = (wintypes.HDC, ctypes.POINTER(BITMAPINFO),
                                   wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
                                   wintypes.HANDLE, wintypes.DWORD)
user32.CreateIconIndirect.restype = wintypes.HICON
user32.CreateIconIndirect.argtypes = (ctypes.POINTER(ICONINFO),)
# без явных argtypes ctypes считает HANDLE обычным int и переполняется на x64
gdi32.CreateBitmap.restype = wintypes.HBITMAP
gdi32.CreateBitmap.argtypes = (ctypes.c_int, ctypes.c_int, wintypes.UINT,
                               wintypes.UINT, ctypes.c_void_p)
gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
user32.DestroyIcon.argtypes = (wintypes.HICON,)
user32.LoadCursorW.restype = wintypes.HANDLE
user32.LoadCursorW.argtypes = (wintypes.HINSTANCE, wintypes.LPCWSTR)
user32.SetTimer.argtypes = (wintypes.HWND, ctypes.c_void_p, wintypes.UINT,
                            ctypes.c_void_p)
user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                wintypes.LPARAM)
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.DestroyMenu.argtypes = (wintypes.HMENU,)
user32.AppendMenuW.argtypes = (wintypes.HMENU, wintypes.UINT, ctypes.c_void_p,
                               wintypes.LPCWSTR)
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)


def _make_icon(size=32):
    """Иконка в памяти: тёмный круг с зелёной каймой. Без файлов и без Pillow."""
    bi = BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = size
    bi.bmiHeader.biHeight = -size  # сверху вниз
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = 0  # BI_RGB

    bits = ctypes.c_void_p()
    dib = gdi32.CreateDIBSection(None, ctypes.byref(bi), 0, ctypes.byref(bits), None, 0)
    if not dib:
        return None

    px = (ctypes.c_uint32 * (size * size)).from_address(bits.value)
    c = (size - 1) / 2.0
    r_out = c
    r_in = c - max(2.0, size / 10.0)
    for y in range(size):
        for x in range(size):
            d = ((x - c) ** 2 + (y - c) ** 2) ** 0.5
            if d > r_out:
                px[y * size + x] = 0x00000000            # прозрачно
            elif d > r_in:
                px[y * size + x] = 0xFF3CC85A            # зелёная кайма (ARGB)
            else:
                px[y * size + x] = 0xFF19191C            # тёмная заливка

    mask = gdi32.CreateBitmap(size, size, 1, 1, None)
    info = ICONINFO(True, 0, 0, mask, dib)
    hicon = user32.CreateIconIndirect(ctypes.byref(info))
    gdi32.DeleteObject(mask)
    gdi32.DeleteObject(dib)
    return hicon


class Tray:
    """Меню в трее.

    `items` — список кортежей (подпись, callback|None[, галочка]). callback=None
    делает пункт неактивным заголовком, подпись "-" — разделителем, а третий
    элемент (bool или функция) рисует галочку.
    """

    def __init__(self, tooltip, items, on_quit):
        self.items = items
        self.on_quit = on_quit
        self._quit_id = 1000
        self._proc = WNDPROC(self._wndproc)  # ссылку держим: иначе GC съест колбэк
        self._timers = {}

        hinst = kernel32.GetModuleHandleW(None)
        cls = WNDCLASSW()
        cls.lpfnWndProc = self._proc
        cls.hInstance = hinst
        cls.lpszClassName = "RazerMacroTrayWnd"
        cls.hCursor = user32.LoadCursorW(None, ctypes.c_wchar_p(IDC_ARROW))
        user32.RegisterClassW(ctypes.byref(cls))

        self.hwnd = user32.CreateWindowExW(0, "RazerMacroTrayWnd", "Razer Macro", 0,
                                           0, 0, 0, 0, HWND_MESSAGE, None, hinst, None)
        self.hicon = _make_icon()

        self.nid = NOTIFYICONDATAW()
        self.nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        self.nid.hWnd = self.hwnd
        self.nid.uID = 1
        self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        self.nid.uCallbackMessage = WM_TRAYICON
        self.nid.hIcon = self.hicon
        self.nid.szTip = tooltip[:127]
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self.nid))

    def set_tooltip(self, text):
        self.nid.szTip = text[:127]
        self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self.nid))

    def set_items(self, items):
        self.items = items

    def add_timer(self, timer_id, period_ms, callback):
        self._timers[timer_id] = callback
        user32.SetTimer(self.hwnd, timer_id, period_ms, None)

    def _show_menu(self):
        menu = user32.CreatePopupMenu()
        for i, item in enumerate(self.items):
            label, cb = item[0], item[1]
            # третий элемент — состояние галочки: bool или функция, которую
            # спрашиваем на каждом открытии меню, чтобы показать актуальное
            checked = item[2] if len(item) > 2 else None
            if callable(checked):
                checked = checked()
            if label == "-":
                user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            else:
                flags = MF_STRING | (0 if cb else MF_GRAYED)
                if checked:
                    flags |= MF_CHECKED
                user32.AppendMenuW(menu, flags, i + 1, label)
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, self._quit_id, "Выход")

        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        # без SetForegroundWindow меню зависает на экране после клика мимо
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD,
                                    pt.x, pt.y, 0, self.hwnd, None)
        user32.DestroyMenu(menu)
        if cmd == self._quit_id:
            self.stop()
        elif cmd:
            callback = self.items[cmd - 1][1]
            if callback:
                callback()

    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            return self._dispatch(hwnd, msg, wparam, lparam)
        except Exception:
            # исключение, вылетевшее в оконную процедуру, роняет процесс целиком
            import traceback
            traceback.print_exc()
            return 0

    def _dispatch(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAYICON:
            if lparam in (WM_RBUTTONUP, WM_LBUTTONDBLCLK):
                self._show_menu()
            return 0
        if msg == WM_TIMER:
            cb = self._timers.get(wparam)
            if cb:
                cb()
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def stop(self):
        """Можно звать из любого потока — работа идёт через оконную очередь."""
        user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    def run(self):
        """Цикл сообщений. Блокирует до выхода; в простое CPU не тратит."""
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
        if self.hicon:
            user32.DestroyIcon(self.hicon)
        self.on_quit()
