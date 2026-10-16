"""Emparejar, olvidar, conectar y desconectar un dispositivo elegido por el usuario."""

from __future__ import annotations

import asyncio
import ctypes
from typing import Any

from bt_scanner.classic import remove_pairing, set_services
from bt_scanner.devices import address_int
from bt_scanner.view import pairing_message, unpair_message

_ASFW_ANY = 0xFFFFFFFF


async def connect_device(device: dict[str, Any], sessions: dict[str, Any]) -> dict[str, Any]:
    address = str(device.get("address") or "")
    kind = str(device.get("kind") or "")
    messages: list[str] = []
    connected = False
    if kind != "ble":
        classic_ok, classic_message = await asyncio.to_thread(set_services, address, True)
        if classic_ok:
            connected = True
            messages.append(classic_message)
        elif kind == "classic" or classic_message.startswith("No se pudo"):
            messages.append(classic_message)
    if not connected and kind != "classic":
        ble_ok, ble_message = await _connect_ble(address, sessions)
        if ble_ok:
            connected = True
        if ble_message:
            messages.append(ble_message)
    if not messages:
        messages.append("No se pudo conectar.")
    return _result(address, connected, " ".join(messages), connected=connected, paired=device.get("paired"))


async def disconnect_device(device: dict[str, Any], sessions: dict[str, Any]) -> dict[str, Any]:
    address = str(device.get("address") or "")
    messages: list[str] = []
    released = sessions.pop(address, None)
    if released is not None:
        messages.append(_close_session(released))
    if device.get("kind") != "ble":
        classic_ok, classic_message = await asyncio.to_thread(set_services, address, False)
        if classic_ok or not classic_message.startswith("No hay servicios"):
            messages.append(classic_message)
        elif not messages:
            messages.append(classic_message)
    closed = any(item.startswith("Desconectado") or item.startswith("Se cerró") for item in messages)
    if not messages:
        messages.append("No había una conexión que cerrar.")
        closed = True
    return _result(address, closed, " ".join(item for item in messages if item), connected=False if closed else None, paired=device.get("paired"))


async def pair_device(device: dict[str, Any]) -> dict[str, Any]:
    address = str(device.get("address") or "")
    _allow_foreground()
    info, opened = await _open_information(device)
    if info is None:
        return _result(address, False, "El dispositivo ya no está visible. Vuelve a escanear.", paired=False)
    try:
        if info.pairing.is_paired:
            return _result(address, True, pairing_message("ALREADY_PAIRED"), paired=True)
        result = await info.pairing.pair_async()
        status = _status_name(result.status)
        ok = status in {"PAIRED", "ALREADY_PAIRED"}
        paired = ok or bool(info.pairing.is_paired)
        return _result(address, ok, pairing_message(status), paired=paired)
    except Exception as exc:
        return _result(address, False, f"No se pudo emparejar. {exc}", paired=False)
    finally:
        _close_opened(opened)


async def unpair_device(device: dict[str, Any], sessions: dict[str, Any]) -> dict[str, Any]:
    address = str(device.get("address") or "")
    released = sessions.pop(address, None)
    if released is not None:
        _close_session(released)
    info, opened = await _open_information(device)
    message = ""
    try:
        if info is not None:
            result = await info.pairing.unpair_async()
            status = _status_name(result.status)
            if status in {"UNPAIRED", "ALREADY_UNPAIRED"}:
                return _result(address, True, unpair_message(status), paired=False, connected=False)
            message = unpair_message(status)
    except Exception as exc:
        message = str(exc)
    finally:
        _close_opened(opened)
    classic_ok, classic_message = await asyncio.to_thread(remove_pairing, address)
    if classic_ok:
        return _result(address, True, classic_message, paired=False, connected=False)
    return _result(address, False, message or classic_message, paired=True)


async def _connect_ble(address: str, sessions: dict[str, Any]) -> tuple[bool, str]:
    import winrt.windows.foundation  # noqa: F401
    from winrt.windows.devices.bluetooth import BluetoothConnectionStatus, BluetoothLEDevice
    from winrt.windows.devices.bluetooth.genericattributeprofile import GattSession

    if address in sessions:
        return True, "Ya hay una conexión BLE abierta por este programa."
    try:
        ble = await BluetoothLEDevice.from_bluetooth_address_async(address_int(address))
    except Exception as exc:
        return False, f"No se pudo abrir el dispositivo BLE. {exc}"
    if ble is None:
        return False, "Windows no encuentra el dispositivo BLE. Vuelve a escanear con él encendido."
    try:
        session = await GattSession.from_device_id_async(ble.bluetooth_device_id)
    except Exception as exc:
        ble.close()
        return False, f"No se pudo preparar la conexión BLE. {exc}"
    if not session.can_maintain_connection:
        session.close()
        ble.close()
        return False, "Este dispositivo no admite una conexión BLE mantenida."
    session.maintain_connection = True
    for _ in range(16):
        if ble.connection_status == BluetoothConnectionStatus.CONNECTED:
            sessions[address] = (session, ble)
            return True, "Conectado por BLE. La conexión sigue mientras este programa esté abierto."
        await asyncio.sleep(0.5)
    session.maintain_connection = False
    session.close()
    ble.close()
    return False, "El dispositivo BLE no respondió. Si no está emparejado, emparéjalo y acércalo."


async def _open_information(device: dict[str, Any]) -> tuple[Any, Any]:
    import winrt.windows.foundation  # noqa: F401
    from winrt.windows.devices.bluetooth import BluetoothDevice, BluetoothLEDevice
    from winrt.windows.devices.enumeration import DeviceInformation, DeviceInformationKind

    seen: list[str] = []
    for device_id in [device.get("device_id"), *(device.get("device_ids") or [])]:
        if device_id and device_id not in seen:
            seen.append(str(device_id))
    for device_id in seen:
        info = await _create_information(DeviceInformation, DeviceInformationKind, device_id)
        if info is not None:
            return info, None
    try:
        numeric = address_int(str(device.get("address") or ""))
    except ValueError:
        return None, None
    for factory in (BluetoothDevice.from_bluetooth_address_async, BluetoothLEDevice.from_bluetooth_address_async):
        try:
            opened = await factory(numeric)
        except Exception:
            continue
        if opened is None:
            continue
        try:
            return opened.device_information, opened
        except Exception:
            _close_opened(opened)
    return None, None


async def _create_information(device_information: Any, kind: Any, device_id: str) -> Any:
    try:
        info = await device_information.create_from_id_async(device_id)
    except Exception:
        info = None
    if info is not None:
        return info
    try:
        return await device_information.create_from_id_async_with_kind_and_additional_properties(
            device_id,
            [],
            kind.ASSOCIATION_ENDPOINT,
        )
    except Exception:
        return None


def _close_session(held: Any) -> str:
    session, ble = held
    try:
        session.maintain_connection = False
        session.close()
        ble.close()
    except Exception as exc:
        return f"No se pudo cerrar la conexión BLE. {exc}"
    return "Se cerró la conexión BLE."


def _close_opened(opened: Any) -> None:
    if opened is None:
        return
    try:
        opened.close()
    except Exception:
        return


def _allow_foreground() -> None:
    try:
        ctypes.windll.user32.AllowSetForegroundWindow(_ASFW_ANY)
    except Exception:
        return


def _status_name(status: Any) -> str:
    return str(getattr(status, "name", status))


def _result(address: str, ok: bool, message: str, **fields: Any) -> dict[str, Any]:
    result = {"ok": ok, "message": message, "address": address}
    result.update(fields)
    return result
