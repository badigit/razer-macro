"""Windows HID через ctypes — замена пакету hidapi.

Нужен ровно тот минимум, которым пользуется демон: перечислить интерфейсы
устройства, открыть, слать/читать feature-репорты и читать input-репорты без
поллинга (overlapped I/O + ожидание на событии).

Зависимостей нет — только stdlib. Это и делает бинарник лёгким.
"""
import ctypes
from ctypes import wintypes

setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
hid = ctypes.WinDLL("hid", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10

ERROR_IO_PENDING = 997
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("InterfaceClassGuid", GUID),
                ("Flags", wintypes.DWORD), ("Reserved", ULONG_PTR)]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Size", wintypes.ULONG), ("VendorID", ctypes.c_ushort),
                ("ProductID", ctypes.c_ushort), ("VersionNumber", ctypes.c_ushort)]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", ctypes.c_ushort), ("UsagePage", ctypes.c_ushort),
        ("InputReportByteLength", ctypes.c_ushort),
        ("OutputReportByteLength", ctypes.c_ushort),
        ("FeatureReportByteLength", ctypes.c_ushort),
        ("Reserved", ctypes.c_ushort * 17),
        ("NumberLinkCollectionNodes", ctypes.c_ushort),
        ("NumberInputButtonCaps", ctypes.c_ushort),
        ("NumberInputValueCaps", ctypes.c_ushort),
        ("NumberInputDataIndices", ctypes.c_ushort),
        ("NumberOutputButtonCaps", ctypes.c_ushort),
        ("NumberOutputValueCaps", ctypes.c_ushort),
        ("NumberOutputDataIndices", ctypes.c_ushort),
        ("NumberFeatureButtonCaps", ctypes.c_ushort),
        ("NumberFeatureValueCaps", ctypes.c_ushort),
        ("NumberFeatureDataIndices", ctypes.c_ushort),
    ]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ULONG_PTR), ("InternalHigh", ULONG_PTR),
                ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD),
                ("hEvent", wintypes.HANDLE)]


setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
setupapi.SetupDiGetClassDevsW.argtypes = (ctypes.POINTER(GUID), wintypes.LPCWSTR,
                                          wintypes.HWND, wintypes.DWORD)
setupapi.SetupDiEnumDeviceInterfaces.argtypes = (
    wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.DWORD,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA))
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = (
    wintypes.HANDLE, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA), ctypes.c_void_p,
    wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p)
setupapi.SetupDiDestroyDeviceInfoList.argtypes = (wintypes.HANDLE,)

hid.HidD_GetHidGuid.argtypes = (ctypes.POINTER(GUID),)
hid.HidD_GetAttributes.argtypes = (wintypes.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES))
hid.HidD_GetPreparsedData.argtypes = (wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p))
hid.HidD_FreePreparsedData.argtypes = (ctypes.c_void_p,)
hid.HidP_GetCaps.argtypes = (ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS))
hid.HidD_SetFeature.argtypes = (wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG)
hid.HidD_GetFeature.argtypes = (wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG)

kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                 ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                 wintypes.HANDLE)
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.CreateEventW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL,
                                  wintypes.LPCWSTR)
kernel32.ReadFile.argtypes = (wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                              ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(OVERLAPPED))
kernel32.GetOverlappedResult.argtypes = (wintypes.HANDLE, ctypes.POINTER(OVERLAPPED),
                                         ctypes.POINTER(wintypes.DWORD), wintypes.BOOL)
kernel32.WaitForMultipleObjects.argtypes = (wintypes.DWORD, ctypes.c_void_p,
                                            wintypes.BOOL, wintypes.DWORD)
kernel32.CancelIo.argtypes = (wintypes.HANDLE,)
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)


def _hid_guid():
    g = GUID()
    hid.HidD_GetHidGuid(ctypes.byref(g))
    return g


def enumerate_devices(vendor_id=None, product_id=None):
    """Список HID-интерфейсов. Каждый — dict с path/vid/pid/usage_page/usage/mi.

    `mi` — номер USB-интерфейса из пути (`&mi_01`), либо None у составных
    устройств без него. Путь нужен как есть: по нему открываем и по подстроке
    `&colNN` различаем коллекции внутри одного интерфейса.
    """
    guid = _hid_guid()
    hdev = setupapi.SetupDiGetClassDevsW(ctypes.byref(guid), None, None,
                                         DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if hdev == INVALID_HANDLE_VALUE:
        return []

    out = []
    try:
        idx = 0
        while True:
            iface = SP_DEVICE_INTERFACE_DATA()
            iface.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
            if not setupapi.SetupDiEnumDeviceInterfaces(hdev, None, ctypes.byref(guid),
                                                        idx, ctypes.byref(iface)):
                break
            idx += 1

            need = wintypes.DWORD(0)
            setupapi.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(iface), None, 0,
                                                      ctypes.byref(need), None)
            if not need.value:
                continue
            buf = ctypes.create_string_buffer(need.value)
            # cbSize у DETAIL_DATA — размер ЗАГОЛОВКА, не буфера: 8 на x64, 6 на x86
            ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD))[0] = (
                8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6)
            if not setupapi.SetupDiGetDeviceInterfaceDetailW(
                    hdev, ctypes.byref(iface), buf, need.value, None, None):
                continue
            path = ctypes.wstring_at(ctypes.addressof(buf) + ctypes.sizeof(wintypes.DWORD))

            info = _probe(path)
            if info is None:
                continue
            if vendor_id is not None and info["vendor_id"] != vendor_id:
                continue
            if product_id is not None and info["product_id"] != product_id:
                continue
            out.append(info)
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(hdev)
    return out


def _probe(path):
    """Открыть интерфейс без прав на данные (dwDesiredAccess=0) и снять паспорт.

    Нулевой доступ важен: так читаются даже те интерфейсы, которые эксклюзивно
    держит система (у клавиатур это обычное дело).
    """
    h = kernel32.CreateFileW(path, 0, FILE_SHARE_READ | FILE_SHARE_WRITE, None,
                             OPEN_EXISTING, 0, None)
    if h == INVALID_HANDLE_VALUE:
        return None
    try:
        attrs = HIDD_ATTRIBUTES()
        attrs.Size = ctypes.sizeof(HIDD_ATTRIBUTES)
        if not hid.HidD_GetAttributes(h, ctypes.byref(attrs)):
            return None

        pre = ctypes.c_void_p()
        caps = HIDP_CAPS()
        if hid.HidD_GetPreparsedData(h, ctypes.byref(pre)):
            try:
                hid.HidP_GetCaps(pre, ctypes.byref(caps))
            finally:
                hid.HidD_FreePreparsedData(pre)

        low = path.lower()
        mi = None
        if "&mi_" in low:
            try:
                mi = int(low.split("&mi_")[1][:2], 16)
            except ValueError:
                mi = None
        return {
            "path": path,
            "vendor_id": attrs.VendorID,
            "product_id": attrs.ProductID,
            "usage_page": caps.UsagePage,
            "usage": caps.Usage,
            "mi": mi,
            "input_len": caps.InputReportByteLength,
            "feature_len": caps.FeatureReportByteLength,
        }
    finally:
        kernel32.CloseHandle(h)


class HidDevice:
    """Открытый HID-интерфейс. Чтение — overlapped, без поллинга."""

    def __init__(self, info):
        self.info = info
        self.path = info["path"]
        self.input_len = info["input_len"] or 65
        self.feature_len = info["feature_len"] or 91
        # Клавиатурные/мышиные коллекции система держит эксклюзивно, и открыть их
        # на чтение данных нельзя. Но HidD_SetFeature/GetFeature работают и с
        # нулевым доступом — именно так до control-интерфейса и добираемся.
        self.readable = True
        for access in (GENERIC_READ | GENERIC_WRITE, GENERIC_READ, 0):
            self.handle = kernel32.CreateFileW(
                self.path, access, FILE_SHARE_READ | FILE_SHARE_WRITE, None,
                OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)
            if self.handle != INVALID_HANDLE_VALUE:
                self.readable = access != 0
                break
        if self.handle == INVALID_HANDLE_VALUE:
            raise OSError(ctypes.get_last_error(), f"CreateFile failed: {self.path}")

        self._event = kernel32.CreateEventW(None, True, False, None)
        self._ov = OVERLAPPED()
        self._ov.hEvent = self._event
        self._buf = ctypes.create_string_buffer(self.input_len)
        self._pending = False

    # ── feature reports ──
    def send_feature(self, payload: bytes):
        buf = ctypes.create_string_buffer(bytes(payload), self.feature_len)
        if not hid.HidD_SetFeature(self.handle, buf, self.feature_len):
            raise OSError(ctypes.get_last_error(), "HidD_SetFeature failed")

    def get_feature(self, report_id=0) -> bytes:
        buf = ctypes.create_string_buffer(self.feature_len)
        buf[0] = bytes([report_id])
        if not hid.HidD_GetFeature(self.handle, buf, self.feature_len):
            raise OSError(ctypes.get_last_error(), "HidD_GetFeature failed")
        return buf.raw

    # ── input reports ──
    def start_read(self):
        """Поставить чтение в очередь. Возвращает False, если устройство отвалилось."""
        if self._pending:
            return True
        kernel32.ResetEvent(self._event)
        read = wintypes.DWORD(0)
        ok = kernel32.ReadFile(self.handle, self._buf, self.input_len,
                               ctypes.byref(read), ctypes.byref(self._ov))
        if ok:
            self._pending = True  # успело синхронно — событие уже взведено
            return True
        if ctypes.get_last_error() == ERROR_IO_PENDING:
            self._pending = True
            return True
        return False

    def complete_read(self):
        """Забрать результат уже готового чтения. None — если данных нет."""
        if not self._pending:
            return None
        read = wintypes.DWORD(0)
        ok = kernel32.GetOverlappedResult(self.handle, ctypes.byref(self._ov),
                                          ctypes.byref(read), False)
        self._pending = False
        if not ok or not read.value:
            return None
        return self._buf.raw[:read.value]

    @property
    def event(self):
        return self._event

    def close(self):
        if self.handle and self.handle != INVALID_HANDLE_VALUE:
            if self._pending:
                kernel32.CancelIo(self.handle)
            kernel32.CloseHandle(self.handle)
            self.handle = None
        if self._event:
            kernel32.CloseHandle(self._event)
            self._event = None


def wait_any(handles, timeout_ms):
    """WaitForMultipleObjects: индекс сработавшего или None по таймауту."""
    n = len(handles)
    arr = (wintypes.HANDLE * n)(*handles)
    r = kernel32.WaitForMultipleObjects(n, arr, False, timeout_ms)
    if WAIT_OBJECT_0 <= r < WAIT_OBJECT_0 + n:
        return r - WAIT_OBJECT_0
    return None
