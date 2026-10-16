"""Canal de texto hacia un Arduino: puerto serie clásico o UART sobre BLE."""

from __future__ import annotations

import asyncio
import queue
import threading
import uuid
from typing import Any

from bt_scanner.devices import address_int

_SERIAL_PORT = uuid.UUID("00001101-0000-1000-8000-00805f9b34fb")
_NUS_SERVICE = uuid.UUID("6e400001-b5a3-f393-e0a9-e50e24dcca9e")
_NUS_WRITE = uuid.UUID("6e400002-b5a3-f393-e0a9-e50e24dcca9e")
_NUS_NOTIFY = uuid.UUID("6e400003-b5a3-f393-e0a9-e50e24dcca9e")
_SKIP_SERVICES = {
    uuid.UUID("00001800-0000-1000-8000-00805f9b34fb"),
    uuid.UUID("00001801-0000-1000-8000-00805f9b34fb"),
    uuid.UUID("0000180a-0000-1000-8000-00805f9b34fb"),
    uuid.UUID("0000180f-0000-1000-8000-00805f9b34fb"),
}
_WRITE_WITHOUT_RESPONSE = 4
_WRITE = 8
_NOTIFY = 16
_INDICATE = 32
_BLE_CHUNK = 20


class ChannelError(Exception):
    """El dispositivo no ofreció un canal de texto usable."""


class Link:
    """Conexión abierta en el hilo de Windows Runtime."""

    def __init__(self, inbox: queue.Queue[tuple[str, Any]]) -> None:
        self.inbox = inbox
        self.description = ""
        self._stop = False
        self._emitted = False
        self._lock = threading.Lock()
        self._task: asyncio.Task[None] | None = None
        self._socket: Any = None
        self._writer: Any = None
        self._reader: Any = None
        self._rfcomm: Any = None
        self._classic: Any = None
        self._ble: Any = None
        self._session: Any = None
        self._services: list[Any] = []
        self._notify: Any = None
        self._write: Any = None
        self._token: Any = None

    async def open(self, device: dict[str, Any]) -> None:
        kind = str(device.get("kind") or "")
        errors: list[str] = []
        if kind != "ble":
            try:
                await self._open_serial(device)
                return
            except Exception as exc:
                errors.append(str(exc) or "No se abrió el puerto serie.")
                await self._release()
        if kind != "classic":
            try:
                await self._open_ble(device)
                return
            except Exception as exc:
                errors.append(str(exc) or "No se abrió el UART BLE.")
                await self._release()
        detail = " ".join(errors)
        raise ChannelError(detail or "No hay un canal de texto en este dispositivo.")

    async def send(self, payload: bytes) -> None:
        if self._stop:
            raise ChannelError("El canal ya está cerrado.")
        if not payload:
            return
        if self._writer is not None:
            self._writer.write_bytes(payload)
            await self._writer.store_async()
            await self._writer.flush_async()
            return
        if self._write is None:
            raise ChannelError("El canal no está abierto.")
        option = _write_option(self._write)
        for offset in range(0, len(payload), _BLE_CHUNK):
            status = await self._write.write_value_with_option_async(
                _bytes_to_buffer(payload[offset : offset + _BLE_CHUNK]),
                option,
            )
            if not _gatt_ok(status):
                raise ChannelError(f"El dispositivo no aceptó el mensaje ({_status_name(status)}).")

    async def close(self) -> None:
        self._stop = True
        task = self._task
        self._task = None
        await self._release()
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        self._emit_closed("")

    async def _open_serial(self, device: dict[str, Any]) -> None:
        import winrt.windows.foundation  # noqa: F401
        from winrt.windows.devices.bluetooth import BluetoothCacheMode, BluetoothDevice
        from winrt.windows.devices.bluetooth.rfcomm import RfcommServiceId
        from winrt.windows.networking.sockets import SocketProtectionLevel, StreamSocket
        from winrt.windows.storage.streams import DataReader, DataWriter, InputStreamOptions

        classic = await BluetoothDevice.from_bluetooth_address_async(address_int(str(device.get("address") or "")))
        if classic is None:
            raise ChannelError("Windows no encuentra el dispositivo clásico. Empárelo y manténgalo encendido.")
        self._classic = classic
        try:
            await classic.request_access_async()
        except Exception:
            pass
        result = await classic.get_rfcomm_services_for_id_with_cache_mode_async(
            RfcommServiceId.serial_port,
            BluetoothCacheMode.UNCACHED,
        )
        raw_services = getattr(result, "services", None)
        services = list(raw_services) if raw_services is not None else []
        if not services:
            raise ChannelError(
                "No ofrece el puerto serie Bluetooth. Sirve para un HC-05, HC-06 o un ESP32 con BluetoothSerial. "
                "Un ESP8266 solo no tiene Bluetooth."
            )
        service = services[0]
        self._rfcomm = service
        socket = StreamSocket()
        self._socket = socket
        await socket.connect_with_protection_level_async(
            service.connection_host_name,
            service.connection_service_name,
            SocketProtectionLevel.BLUETOOTH_ENCRYPTION_ALLOW_NULL_AUTHENTICATION,
        )
        self._writer = DataWriter(socket.output_stream)
        reader = DataReader(socket.input_stream)
        reader.input_stream_options = InputStreamOptions.PARTIAL
        self._reader = reader
        self.description = "Escuchando el puerto serie Bluetooth."
        self._task = asyncio.create_task(self._read_serial())

    async def _read_serial(self) -> None:
        try:
            while not self._stop:
                loaded = int(await self._reader.load_async(256))
                if loaded <= 0:
                    break
                buffer = self._reader.read_buffer(loaded)
                data = _buffer_bytes(buffer, loaded)
                if data:
                    self.inbox.put(("data", data))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self._stop:
                self._emit_closed(f"Se cortó la escucha. {exc}")
                return
        self._emit_closed("" if self._stop else "El dispositivo cerró el canal.")

    async def _open_ble(self, device: dict[str, Any]) -> None:
        import winrt.windows.foundation  # noqa: F401
        from winrt.windows.devices.bluetooth import BluetoothCacheMode, BluetoothLEDevice
        from winrt.windows.devices.bluetooth.genericattributeprofile import (
            GattClientCharacteristicConfigurationDescriptorValue,
            GattSession,
        )

        ble = await BluetoothLEDevice.from_bluetooth_address_async(address_int(str(device.get("address") or "")))
        if ble is None:
            raise ChannelError("Windows no encuentra el dispositivo BLE. Tiene que estar anunciando.")
        self._ble = ble
        try:
            await ble.request_access_async()
        except Exception:
            pass
        session = await GattSession.from_device_id_async(ble.bluetooth_device_id)
        self._session = session
        if session.can_maintain_connection:
            session.maintain_connection = True
        result = await ble.get_gatt_services_with_cache_mode_async(BluetoothCacheMode.UNCACHED)
        if not _gatt_ok(result.status):
            raise ChannelError(f"No se pudieron leer los servicios BLE ({_status_name(result.status)}).")
        self._services = list(result.services or [])
        write, notify, label = await self._pick_ble_pair(self._services)
        mode = (
            GattClientCharacteristicConfigurationDescriptorValue.NOTIFY
            if int(notify.characteristic_properties) & _NOTIFY
            else GattClientCharacteristicConfigurationDescriptorValue.INDICATE
        )
        self._write = write
        self._notify = notify
        status = await notify.write_client_characteristic_configuration_descriptor_async(mode)
        if not _gatt_ok(status):
            raise ChannelError(f"No se pudo suscribir a los avisos BLE ({_status_name(status)}).")
        self._token = notify.add_value_changed(self._on_notify)
        self.description = label

    async def _pick_ble_pair(self, services: list[Any]) -> tuple[Any, Any, str]:
        from winrt.windows.devices.bluetooth import BluetoothCacheMode

        pairs: list[tuple[Any, Any, Any, str]] = []
        for service in services:
            result = await service.get_characteristics_with_cache_mode_async(BluetoothCacheMode.UNCACHED)
            if not _gatt_ok(result.status):
                continue
            chars = list(result.characteristics)
            service_id = _uuid_of(service)
            write = _find_uuid(chars, _NUS_WRITE) or _first(chars, _can_write)
            notify = _find_uuid(chars, _NUS_NOTIFY) or _first(chars, _can_notify)
            if service_id == _NUS_SERVICE and write is not None and notify is not None:
                return write, notify, "Escuchando el UART BLE (Nordic)."
            if service_id in _SKIP_SERVICES or write is None or notify is None:
                continue
            pairs.append((service, write, notify, service_id))
        if not pairs:
            raise ChannelError(
                "No hay un canal de texto BLE. El sketch tiene que anunciar el UART Nordic "
                "(6E400001) o un servicio propio con una característica de escritura y otra de aviso."
            )
        _service, write, notify, service_id = pairs[0]
        return write, notify, f"Escuchando un servicio BLE propio ({service_id})."

    def _on_notify(self, _sender: Any, args: Any) -> None:
        if self._stop:
            return
        data = _buffer_bytes(args.characteristic_value, None)
        if data:
            self.inbox.put(("data", data))

    async def _release(self) -> None:
        notify = self._notify
        token = self._token
        self._token = None
        if notify is not None and token is not None:
            try:
                notify.remove_value_changed(token)
            except Exception:
                pass
            try:
                from winrt.windows.devices.bluetooth.genericattributeprofile import (
                    GattClientCharacteristicConfigurationDescriptorValue,
                )

                await notify.write_client_characteristic_configuration_descriptor_async(
                    GattClientCharacteristicConfigurationDescriptorValue.NONE
                )
            except Exception:
                pass
        self._notify = None
        self._write = None
        for obj in (self._reader, self._writer, self._socket, self._rfcomm, self._classic, self._session, self._ble, *self._services):
            _safe_close(obj)
        self._reader = None
        self._writer = None
        self._socket = None
        self._rfcomm = None
        self._classic = None
        self._session = None
        self._ble = None
        self._services = []

    def _emit_closed(self, status: str) -> None:
        with self._lock:
            if self._emitted:
                return
            self._emitted = True
        if status:
            self.inbox.put(("status", status))
        self.inbox.put(("closed", ""))


def _gatt_ok(status: Any) -> bool:
    if status == 0:
        return True
    return getattr(status, "name", "") == "SUCCESS"


def _status_name(status: Any) -> str:
    name = getattr(status, "name", None)
    return str(name if name else status)


def _find_uuid(chars: list[Any], target: uuid.UUID) -> Any:
    for char in chars:
        if _uuid_of(char) == target:
            return char
    return None


def _first(chars: list[Any], test: Any) -> Any:
    for char in chars:
        if test(char):
            return char
    return None


def _uuid_of(obj: Any) -> uuid.UUID:
    value = obj.uuid
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _can_write(char: Any) -> bool:
    props = int(char.characteristic_properties)
    return bool(props & (_WRITE | _WRITE_WITHOUT_RESPONSE))


def _can_notify(char: Any) -> bool:
    return bool(int(char.characteristic_properties) & (_NOTIFY | _INDICATE))


def _write_option(char: Any) -> Any:
    from winrt.windows.devices.bluetooth.genericattributeprofile import GattWriteOption

    if int(char.characteristic_properties) & _WRITE_WITHOUT_RESPONSE:
        return GattWriteOption.WRITE_WITHOUT_RESPONSE
    return GattWriteOption.WRITE_WITH_RESPONSE


def _bytes_to_buffer(payload: bytes) -> Any:
    from winrt.windows.storage.streams import DataWriter

    writer = DataWriter()
    writer.write_bytes(payload)
    return writer.detach_buffer()


def _buffer_bytes(buffer: Any, expected: int | None) -> bytes:
    if buffer is None:
        return b""
    try:
        raw = bytes(buffer)
    except Exception:
        return b""
    length = expected
    reported = getattr(buffer, "length", None)
    if reported is not None:
        length = int(reported)
    if length is None:
        return raw
    return raw[:length]


def _safe_close(obj: Any) -> None:
    if obj is None:
        return
    try:
        obj.close()
    except Exception:
        return
