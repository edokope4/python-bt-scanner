"""Barrido de dispositivos Bluetooth cercanos y emparejados en Windows."""

from __future__ import annotations

import sys
import threading
import time
from datetime import datetime
from typing import Any

from bt_scanner import __version__
from bt_scanner.classic import radio_facts, remembered_devices
from bt_scanner.devices import (
    clean_name,
    format_address,
    merge_devices,
    normalize_uuid,
    parse_address,
    recount,
)

SCAN_SECONDS = 8.0

_PROPS = [
    "System.Devices.Aep.DeviceAddress",
    "System.Devices.Aep.IsConnected",
    "System.Devices.Aep.IsPaired",
    "System.Devices.Aep.IsPresent",
    "System.Devices.Aep.SignalStrength",
    "System.Devices.Aep.CanPair",
    "System.Devices.Aep.Category",
    "System.Devices.Aep.Bluetooth.Le.IsConnectable",
    "System.Devices.Aep.Bluetooth.Cod.Major",
    "System.Devices.Aep.Bluetooth.Cod.Minor",
    "System.Devices.Aep.Bluetooth.Le.Appearance.Category",
    "System.Devices.Aep.Bluetooth.LastSeenTime",
    "System.ItemNameDisplay",
]

_CLASSIC_AEP = 'System.Devices.Aep.ProtocolId:="{e0cbf06c-cd8b-4647-bb8a-263b43f0f974}"'
_BLE_AEP = 'System.Devices.Aep.ProtocolId:="{bb7bb05e-5972-42b5-94fc-76eaa7084d49}"'


async def scan_async(*, refresh: bool = True, duration: float = SCAN_SECONDS) -> dict[str, Any]:
    """Lee el adaptador y los dispositivos. `refresh` pide un barrido de los cercanos."""
    started = time.perf_counter()
    warnings: list[str] = []
    error = None
    records: list[dict[str, Any]] = []
    if sys.platform != "win32":
        radio = {"name": "Bluetooth", "state": "missing", "classic": False, "ble": False}
        error = "Este programa detecta Bluetooth solo en Windows."
    else:
        radio = await _radio()
        if radio.get("state") == "missing":
            error = "No se detectó un adaptador Bluetooth."
        else:
            if radio.get("state") == "off":
                warnings.append("El Bluetooth está apagado.")
            elif radio.get("state") == "disabled":
                warnings.append("El Bluetooth está desactivado.")
            records.extend(_safe_remembered(warnings))
            try:
                records.extend(await _paired_records())
            except Exception as exc:
                warnings.append(f"No se pudo leer los dispositivos emparejados: {exc}")
            if refresh and radio.get("state") == "on":
                try:
                    live, live_warnings = await _live(duration)
                except Exception as exc:
                    live = []
                    live_warnings = [f"No se pudo buscar dispositivos cercanos: {exc}"]
                warnings.extend(live_warnings)
                records.extend(live)
    devices = merge_devices(records)
    if refresh and not devices and not error and radio.get("state") == "on":
        warnings.append(
            "No apareció ningún dispositivo. Si esperabas equipos cercanos, activa la ubicación "
            "del sistema: Windows la usa para el barrido Bluetooth LE."
        )
    return {
        "ok": error is None,
        "error": error,
        "warnings": [item for item in warnings if item],
        "radio": radio,
        "devices": devices,
        "counts": recount(devices),
        "scanned_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "refresh": refresh,
        "version": __version__,
    }


def _safe_remembered(warnings: list[str]) -> list[dict[str, Any]]:
    try:
        return remembered_devices()
    except Exception as exc:
        warnings.append(f"No se pudo leer los dispositivos recordados: {exc}")
        return []


async def _radio() -> dict[str, Any]:
    import winrt.windows.foundation  # noqa: F401
    from winrt.windows.devices.bluetooth import BluetoothAdapter
    from winrt.windows.devices.radios import Radio, RadioKind, RadioState

    facts: dict[str, Any] = {"name": "Bluetooth", "state": "missing", "classic": False, "ble": False}
    try:
        facts.update(radio_facts())
    except Exception:
        pass
    radios = await Radio.get_radios_async()
    bluetooth = next((item for item in radios if item.kind == RadioKind.BLUETOOTH), None)
    if bluetooth is None:
        return facts
    facts["name"] = bluetooth.name or "Bluetooth"
    if bluetooth.state == RadioState.ON:
        facts["state"] = "on"
    elif bluetooth.state == RadioState.OFF:
        facts["state"] = "off"
    elif bluetooth.state == RadioState.DISABLED:
        facts["state"] = "disabled"
    else:
        facts["state"] = "unknown"
    adapter = await BluetoothAdapter.get_default_async()
    if adapter is not None:
        facts["classic"] = bool(adapter.is_classic_supported)
        facts["ble"] = bool(adapter.is_low_energy_supported)
        if adapter.bluetooth_address and not facts.get("address"):
            facts["address"] = format_address(int(adapter.bluetooth_address))
    return facts


async def _paired_records() -> list[dict[str, Any]]:
    import winrt.windows.foundation  # noqa: F401
    from winrt.windows.devices.bluetooth import BluetoothDevice, BluetoothLEDevice
    from winrt.windows.devices.enumeration import DeviceInformation

    records: list[dict[str, Any]] = []
    queries = (
        (BluetoothDevice.get_device_selector_from_pairing_state(True), "classic"),
        (BluetoothLEDevice.get_device_selector_from_pairing_state(True), "ble"),
    )
    for selector, kind in queries:
        found = await DeviceInformation.find_all_async_aqs_filter_and_additional_properties(selector, _PROPS)
        for info in found:
            patch = _from_info(info, kind)
            if patch:
                records.append(patch)
    return records


async def _live(duration: float) -> tuple[list[dict[str, Any]], list[str]]:
    import winrt.windows.foundation  # noqa: F401
    import asyncio
    from winrt.windows.devices.bluetooth.advertisement import (
        BluetoothLEAdvertisementWatcher,
        BluetoothLEAdvertisementWatcherStatus,
        BluetoothLEScanningMode,
    )
    from winrt.windows.devices.enumeration import DeviceInformation, DeviceInformationKind

    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    lock = threading.Lock()

    def add(patch: dict[str, Any] | None) -> None:
        if patch and patch.get("address"):
            with lock:
                records.append(patch)

    watcher = BluetoothLEAdvertisementWatcher()
    watcher.scanning_mode = BluetoothLEScanningMode.ACTIVE
    try:
        watcher.allow_extended_advertisements = True
    except Exception:
        pass

    def on_advertisement(_sender: object, args: object) -> None:
        try:
            add(_from_advertisement(args))
        except Exception:
            return

    def on_stopped(_sender: object, args: object) -> None:
        error = getattr(args, "error", None)
        name = getattr(error, "name", "")
        if error not in (None, 0) and name not in ("", "SUCCESS"):
            with lock:
                warnings.append(f"El barrido BLE se detuvo: {name or error}.")

    watcher.add_received(on_advertisement)
    watcher.add_stopped(on_stopped)

    endpoint = DeviceInformationKind.ASSOCIATION_ENDPOINT
    classic = DeviceInformation.create_watcher_with_kind_aqs_filter_and_additional_properties(
        _CLASSIC_AEP,
        [*_PROPS, "System.Devices.Aep.Bluetooth.IssueInquiry"],
        endpoint,
    )
    ble = DeviceInformation.create_watcher_with_kind_aqs_filter_and_additional_properties(
        _BLE_AEP,
        _PROPS,
        endpoint,
    )
    classic.add_added(lambda _sender, info: add(_safe_info(info, "classic")))
    classic.add_updated(lambda _sender, update: add(_from_update(update, "classic")))
    ble.add_added(lambda _sender, info: add(_safe_info(info, "ble")))
    ble.add_updated(lambda _sender, update: add(_from_update(update, "ble")))

    started = []
    try:
        watcher.start()
        started.append(watcher)
        classic.start()
        started.append(classic)
        ble.start()
        started.append(ble)
        await asyncio.sleep(duration)
    finally:
        for item in reversed(started):
            try:
                item.stop()
            except Exception:
                pass
    if watcher.status == BluetoothLEAdvertisementWatcherStatus.ABORTED and not warnings:
        warnings.append("El adaptador interrumpió el barrido BLE.")
    return records, warnings


def _safe_info(info: object, kind: str) -> dict[str, Any] | None:
    try:
        return _from_info(info, kind)
    except Exception:
        return None


def _from_info(info: Any, kind: str) -> dict[str, Any] | None:
    props = _mapping(info.properties)
    address = parse_address(str(props.get("System.Devices.Aep.DeviceAddress") or "")) or _address_from_id(str(info.id))
    if not address:
        return None
    patch = _fields_from_props(props, address, str(info.id), kind, str(info.name or ""))
    try:
        patch["paired"] = bool(info.pairing.is_paired)
        patch["can_pair"] = bool(info.pairing.can_pair)
    except Exception:
        pass
    return patch


def _from_update(update: Any, kind: str) -> dict[str, Any] | None:
    try:
        props = _mapping(update.properties)
    except Exception:
        return None
    address = parse_address(str(props.get("System.Devices.Aep.DeviceAddress") or "")) or _address_from_id(str(update.id))
    if not address:
        return None
    return _fields_from_props(props, address, str(update.id), kind, "")


def _fields_from_props(props: dict[str, Any], address: str, device_id: str, kind: str, name: str) -> dict[str, Any]:
    patch: dict[str, Any] = {
        "address": address,
        "kind": kind,
        "device_id": device_id,
        "name": clean_name(str(props.get("System.ItemNameDisplay") or name), address),
    }
    if "System.Devices.Aep.IsConnected" in props:
        patch["connected"] = bool(props["System.Devices.Aep.IsConnected"])
    if "System.Devices.Aep.IsPaired" in props:
        patch["paired"] = bool(props["System.Devices.Aep.IsPaired"])
    if "System.Devices.Aep.IsPresent" in props:
        patch["present"] = bool(props["System.Devices.Aep.IsPresent"])
    if "System.Devices.Aep.CanPair" in props:
        patch["can_pair"] = bool(props["System.Devices.Aep.CanPair"])
    if kind == "ble" and "System.Devices.Aep.Bluetooth.Le.IsConnectable" in props:
        patch["connectable"] = bool(props["System.Devices.Aep.Bluetooth.Le.IsConnectable"])
    signal = props.get("System.Devices.Aep.SignalStrength")
    if isinstance(signal, (int, float)):
        patch["rssi"] = int(signal)
    major = props.get("System.Devices.Aep.Bluetooth.Cod.Major")
    minor = props.get("System.Devices.Aep.Bluetooth.Cod.Minor")
    if isinstance(major, int):
        patch["cod_major"] = major
    if isinstance(minor, int):
        patch["cod_minor"] = minor
    appearance = props.get("System.Devices.Aep.Bluetooth.Le.Appearance.Category")
    if isinstance(appearance, int):
        patch["appearance"] = appearance
    seen = props.get("System.Devices.Aep.Bluetooth.LastSeenTime")
    if isinstance(seen, datetime):
        patch["last_seen"] = seen.isoformat()
    category = props.get("System.Devices.Aep.Category")
    if isinstance(category, (list, tuple)):
        patch["category"] = ", ".join(str(item) for item in category if item)
    elif isinstance(category, str) and category:
        patch["category"] = category
    return patch


def _from_advertisement(args: Any) -> dict[str, Any]:
    from winrt.windows.devices.bluetooth import BluetoothAddressType
    from winrt.windows.devices.bluetooth.advertisement import BluetoothLEAdvertisementDataTypes

    address = format_address(int(args.bluetooth_address))
    flags = int(args.advertisement.flags or 0)
    kind = "dual" if flags & 0x18 else "ble"
    services = [normalize_uuid(str(item)) for item in args.advertisement.service_uuids]
    company_id = None
    payload = ""
    for item in args.advertisement.manufacturer_data:
        company_id = int(item.company_id)
        raw = _buffer_bytes(item.data)
        if raw:
            payload = " ".join(f"{byte:02X}" for byte in raw[:24])
        break
    patch: dict[str, Any] = {
        "address": address,
        "name": str(args.advertisement.local_name or ""),
        "kind": kind,
        "rssi": int(args.raw_signal_strength_in_dbm),
        "present": True,
        "services": services,
        "flags": flags,
        "address_type": {
            BluetoothAddressType.PUBLIC: "public",
            BluetoothAddressType.RANDOM: "random",
            BluetoothAddressType.UNSPECIFIED: "unspecified",
        }.get(args.bluetooth_address_type, ""),
    }
    if company_id is not None:
        patch["company_id"] = company_id
    if payload:
        patch["manufacturer_hex"] = payload
    appearance = _appearance(args.advertisement, BluetoothLEAdvertisementDataTypes.appearance)
    if appearance is not None:
        patch["appearance"] = appearance
    if args.transmit_power_level_in_dbm is not None:
        patch["tx_power"] = int(args.transmit_power_level_in_dbm)
    if args.is_connectable is not None:
        patch["connectable"] = bool(args.is_connectable)
    timestamp = getattr(args, "timestamp", None)
    if isinstance(timestamp, datetime):
        patch["last_seen"] = timestamp.isoformat()
    return patch


def _appearance(advertisement: Any, data_type: int) -> int | None:
    try:
        sections = advertisement.get_sections_by_type(data_type)
    except Exception:
        return None
    for section in sections:
        raw = _buffer_bytes(section.data)
        if len(raw) >= 2:
            category = (raw[0] | (raw[1] << 8)) >> 6
            return category or None
    return None


def _address_from_id(device_id: str) -> str:
    import re

    found = re.findall(r"[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}", device_id)
    if not found:
        return ""
    return parse_address(found[-1])


def _mapping(properties: Any) -> dict[str, Any]:
    found: dict[str, Any] = {}
    try:
        items = list(properties.items())
    except Exception:
        return found
    for key, value in items:
        found[str(key)] = _unbox(value)
    return found


def _unbox(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    from winrt.windows.foundation import IPropertyValue, PropertyType

    try:
        prop = value.as_(IPropertyValue)
    except Exception:
        return None
    readers = {
        PropertyType.BOOLEAN: prop.get_boolean,
        PropertyType.UINT8: prop.get_uint8,
        PropertyType.INT16: prop.get_int16,
        PropertyType.UINT16: prop.get_uint16,
        PropertyType.INT32: prop.get_int32,
        PropertyType.UINT32: prop.get_uint32,
        PropertyType.INT64: prop.get_int64,
        PropertyType.UINT64: prop.get_uint64,
        PropertyType.STRING: prop.get_string,
        PropertyType.DATE_TIME: prop.get_date_time,
        PropertyType.STRING_ARRAY: prop.get_string_array,
    }
    reader = readers.get(prop.type)
    if reader is None:
        return None
    try:
        result = reader()
    except Exception:
        return None
    if prop.type == PropertyType.STRING_ARRAY:
        return [str(item) for item in result]
    return result


def _buffer_bytes(data: Any) -> bytes:
    if data is None:
        return b""
    length = getattr(data, "length", None)
    try:
        raw = bytes(data)
    except Exception:
        try:
            raw = bytes(memoryview(data))
        except Exception:
            return b""
    if length is not None:
        raw = raw[: int(length)]
    return raw[:48]
