"""Consulta y conexión de dispositivos Bluetooth clásicos con BluetoothAPIs."""

from __future__ import annotations

import ctypes
import uuid
from ctypes import wintypes
from typing import Any, Iterator

from bt_scanner.devices import format_address

_ENABLE = 0x0001
_DISABLE = 0x0000
_ERROR_MORE_DATA = 234


class _SystemTime(ctypes.Structure):
    _fields_ = [
        ("wYear", wintypes.WORD),
        ("wMonth", wintypes.WORD),
        ("wDayOfWeek", wintypes.WORD),
        ("wDay", wintypes.WORD),
        ("wHour", wintypes.WORD),
        ("wMinute", wintypes.WORD),
        ("wSecond", wintypes.WORD),
        ("wMilliseconds", wintypes.WORD),
    ]


class _Address(ctypes.Union):
    _fields_ = [("ullLong", ctypes.c_ulonglong), ("rgBytes", ctypes.c_ubyte * 6)]


class _DeviceInfo(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("Address", _Address),
        ("ulClassofDevice", wintypes.ULONG),
        ("fConnected", wintypes.BOOL),
        ("fRemembered", wintypes.BOOL),
        ("fAuthenticated", wintypes.BOOL),
        ("stLastSeen", _SystemTime),
        ("stLastUsed", _SystemTime),
        ("szName", ctypes.c_wchar * 248),
    ]


class _RadioParams(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD)]


class _RadioInfo(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("address", _Address),
        ("szName", ctypes.c_wchar * 248),
        ("ulClassofDevice", wintypes.ULONG),
        ("lmpSubversion", wintypes.USHORT),
        ("manufacturer", wintypes.USHORT),
    ]


class _SearchParams(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("fReturnAuthenticated", wintypes.BOOL),
        ("fReturnRemembered", wintypes.BOOL),
        ("fReturnUnknown", wintypes.BOOL),
        ("fReturnConnected", wintypes.BOOL),
        ("fIssueInquiry", wintypes.BOOL),
        ("cTimeoutMultiplier", ctypes.c_ubyte),
        ("hRadio", wintypes.HANDLE),
    ]


class _Guid(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def guid_to_text(guid: _Guid) -> str:
    raw = ctypes.string_at(ctypes.addressof(guid), ctypes.sizeof(guid))
    return str(uuid.UUID(bytes_le=raw))


def radio_facts() -> dict[str, Any]:
    """Nombre local, dirección y si el adaptador es visible. Vacío si no hay radio."""
    facts: dict[str, Any] = {}
    try:
        with _open_radio() as radio:
            facts.update(_radio_info(radio))
            facts["discoverable"] = bool(_api().BluetoothIsDiscoverable(radio))
            facts["connectable"] = bool(_api().BluetoothIsConnectable(radio))
    except OSError:
        return {}
    return facts


def remembered_devices() -> list[dict[str, Any]]:
    """Dispositivos que Windows ya recuerda, sin iniciar una búsqueda nueva."""
    found: list[dict[str, Any]] = []
    try:
        with _open_radio() as radio:
            for info in _iterate_remembered(radio):
                found.append(_device_patch(radio, info))
    except OSError:
        return []
    return found


def set_services(address: str, enabled: bool) -> tuple[bool, str]:
    """Activa o desactiva los servicios clásicos instalados para un dispositivo emparejado."""
    try:
        with _open_radio() as radio:
            info = _info_for(radio, address)
            if info is None:
                return False, "Windows no tiene este dispositivo entre los recordados. Empárelo primero."
            services = _service_guids(radio, info)
            if not services:
                return False, "No hay servicios Bluetooth clásicos instalados para este dispositivo."
            failures: list[str] = []
            done = 0
            for service in services:
                code = _api().BluetoothSetServiceState(radio, ctypes.byref(info), ctypes.byref(service), _ENABLE if enabled else _DISABLE)
                if code == 0:
                    done += 1
                else:
                    failures.append(_error_text(code))
            if done == 0:
                detail = failures[0] if failures else "Windows no cambió el estado."
                verb = "conectar" if enabled else "desconectar"
                return False, f"No se pudo {verb}. {detail}"
            action = "activaron" if enabled else "desactivaron"
            noun = "servicio" if done == 1 else "servicios"
            if enabled:
                return True, f"Conectado. Se {action} {done} {noun}."
            return True, f"Desconectado. Se {action} {done} {noun}."
    except OSError as exc:
        return False, str(exc)


def remove_pairing(address: str) -> tuple[bool, str]:
    numeric = int(address.replace(":", ""), 16)
    target = _Address(ullLong=numeric)
    code = _api().BluetoothRemoveDevice(ctypes.byref(target))
    if code == 0:
        return True, "Se olvidó el dispositivo."
    return False, _error_text(code)


def _device_patch(radio: wintypes.HANDLE, info: _DeviceInfo) -> dict[str, Any]:
    raw = int(info.ulClassofDevice)
    patch: dict[str, Any] = {
        "address": format_address(int(info.Address.ullLong)),
        "name": str(info.szName or ""),
        "kind": "classic",
        "paired": bool(info.fRemembered or info.fAuthenticated),
        "connected": bool(info.fConnected),
        "cod_major": (raw >> 8) & 0x1F,
        "cod_minor": (raw >> 2) & 0x3F,
        "services": _service_uuids(radio, info),
    }
    return patch


def _service_uuids(radio: wintypes.HANDLE, info: _DeviceInfo) -> list[str]:
    return [guid_to_text(item) for item in _service_guids(radio, info)]


def _service_guids(radio: wintypes.HANDLE, info: _DeviceInfo) -> list[_Guid]:
    count = wintypes.DWORD(0)
    code = _api().BluetoothEnumerateInstalledServices(radio, ctypes.byref(info), ctypes.byref(count), None)
    if count.value <= 0 or code not in (0, _ERROR_MORE_DATA):
        return []
    array = (_Guid * int(count.value))()
    code = _api().BluetoothEnumerateInstalledServices(radio, ctypes.byref(info), ctypes.byref(count), array)
    if code != 0:
        return []
    return list(array)


def _info_for(radio: wintypes.HANDLE, address: str) -> _DeviceInfo | None:
    info = _DeviceInfo()
    info.dwSize = ctypes.sizeof(_DeviceInfo)
    info.Address.ullLong = int(address.replace(":", ""), 16)
    code = _api().BluetoothGetDeviceInfo(radio, ctypes.byref(info))
    if code != 0:
        return None
    return info


def _iterate_remembered(radio: wintypes.HANDLE) -> Iterator[_DeviceInfo]:
    params = _SearchParams()
    params.dwSize = ctypes.sizeof(_SearchParams)
    params.fReturnAuthenticated = True
    params.fReturnRemembered = True
    params.fReturnUnknown = False
    params.fReturnConnected = True
    params.fIssueInquiry = False
    params.hRadio = radio
    info = _DeviceInfo()
    info.dwSize = ctypes.sizeof(_DeviceInfo)
    handle = _api().BluetoothFindFirstDevice(ctypes.byref(params), ctypes.byref(info))
    if not handle:
        return
    try:
        while True:
            yield info
            info = _DeviceInfo()
            info.dwSize = ctypes.sizeof(_DeviceInfo)
            if not _api().BluetoothFindNextDevice(handle, ctypes.byref(info)):
                return
    finally:
        _api().BluetoothFindDeviceClose(handle)


def _radio_info(radio: wintypes.HANDLE) -> dict[str, Any]:
    info = _RadioInfo()
    info.dwSize = ctypes.sizeof(_RadioInfo)
    code = _api().BluetoothGetRadioInfo(radio, ctypes.byref(info))
    if code != 0:
        return {}
    facts: dict[str, Any] = {}
    if info.szName:
        facts["local_name"] = str(info.szName)
    if info.address.ullLong:
        facts["address"] = format_address(int(info.address.ullLong))
    if info.manufacturer:
        facts["manufacturer"] = int(info.manufacturer)
    return facts


def _error_text(code: int) -> str:
    try:
        text = ctypes.WinError(int(code)).strerror or ""
    except OSError:
        text = ""
    text = " ".join(text.split())
    if text:
        return text
    return f"Código de Windows {code}."


def _open_radio():
    return _Radio()


class _Radio:
    def __init__(self) -> None:
        params = _RadioParams(ctypes.sizeof(_RadioParams))
        self.handle = wintypes.HANDLE()
        self._find = _api().BluetoothFindFirstRadio(ctypes.byref(params), ctypes.byref(self.handle))
        if not self._find or not self.handle:
            raise OSError("No se encontró un adaptador Bluetooth.")

    def __enter__(self) -> wintypes.HANDLE:
        return self.handle

    def __exit__(self, *_args: object) -> None:
        if self._find:
            _api().BluetoothFindRadioClose(self._find)
        if self.handle:
            ctypes.windll.kernel32.CloseHandle(self.handle)


_LIBRARY = None


def _api():
    global _LIBRARY
    if _LIBRARY is None:
        library = ctypes.WinDLL("BluetoothAPIs")
        _bind(library)
        _LIBRARY = library
    return _LIBRARY


def _bind(library: ctypes.WinDLL) -> None:
    library.BluetoothFindFirstRadio.argtypes = [ctypes.POINTER(_RadioParams), ctypes.POINTER(wintypes.HANDLE)]
    library.BluetoothFindFirstRadio.restype = wintypes.HANDLE
    library.BluetoothFindRadioClose.argtypes = [wintypes.HANDLE]
    library.BluetoothFindRadioClose.restype = wintypes.BOOL
    library.BluetoothGetRadioInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_RadioInfo)]
    library.BluetoothGetRadioInfo.restype = wintypes.DWORD
    library.BluetoothIsDiscoverable.argtypes = [wintypes.HANDLE]
    library.BluetoothIsDiscoverable.restype = wintypes.BOOL
    library.BluetoothIsConnectable.argtypes = [wintypes.HANDLE]
    library.BluetoothIsConnectable.restype = wintypes.BOOL
    library.BluetoothGetDeviceInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_DeviceInfo)]
    library.BluetoothGetDeviceInfo.restype = wintypes.DWORD
    library.BluetoothFindFirstDevice.argtypes = [ctypes.POINTER(_SearchParams), ctypes.POINTER(_DeviceInfo)]
    library.BluetoothFindFirstDevice.restype = wintypes.HANDLE
    library.BluetoothFindNextDevice.argtypes = [wintypes.HANDLE, ctypes.POINTER(_DeviceInfo)]
    library.BluetoothFindNextDevice.restype = wintypes.BOOL
    library.BluetoothFindDeviceClose.argtypes = [wintypes.HANDLE]
    library.BluetoothFindDeviceClose.restype = wintypes.BOOL
    library.BluetoothEnumerateInstalledServices.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_DeviceInfo),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(_Guid),
    ]
    library.BluetoothEnumerateInstalledServices.restype = wintypes.DWORD
    library.BluetoothSetServiceState.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_DeviceInfo),
        ctypes.POINTER(_Guid),
        wintypes.DWORD,
    ]
    library.BluetoothSetServiceState.restype = wintypes.DWORD
    library.BluetoothRemoveDevice.argtypes = [ctypes.POINTER(_Address)]
    library.BluetoothRemoveDevice.restype = wintypes.DWORD
