"""Texto y orden de la lista de dispositivos, sin depender de la ventana."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bt_scanner.catalog import appearance_label, class_label, company_name, service_name

_HID_SERVICES = {
    "00001124-0000-1000-8000-00805f9b34fb",
    "00001812-0000-1000-8000-00805f9b34fb",
}

_PAIRING = {
    "PAIRED": "Emparejado.",
    "ALREADY_PAIRED": "Ya estaba emparejado.",
    "PAIRING_CANCELED": "Se canceló el emparejamiento.",
    "AUTHENTICATION_TIMEOUT": "El dispositivo no respondió a tiempo.",
    "AUTHENTICATION_FAILURE": "No se aceptó la autenticación.",
    "AUTHENTICATION_NOT_ALLOWED": "El dispositivo no permite autenticarse.",
    "CONNECTION_REJECTED": "El dispositivo rechazó la conexión.",
    "NOT_READY_TO_PAIR": "No está listo para emparejarse. Acércalo y vuelve a escanear.",
    "NOT_PAIRED": "No se completó el emparejamiento.",
    "NO_SUPPORTED_PROFILES": "Windows no tiene un perfil compatible.",
    "ACCESS_DENIED": "Windows denegó el emparejamiento.",
    "HARDWARE_FAILURE": "Falló el adaptador Bluetooth.",
    "TOO_MANY_CONNECTIONS": "Hay demasiadas conexiones abiertas.",
    "OPERATION_ALREADY_IN_PROGRESS": "Ya hay un emparejamiento en curso.",
    "REJECTED_BY_HANDLER": "Se rechazó el emparejamiento.",
    "PROTECTION_LEVEL_COULD_NOT_BE_MET": "No se alcanzó el nivel de protección que pide el dispositivo.",
    "REMOTE_DEVICE_HAS_ASSOCIATION": "El dispositivo ya está asociado a otro equipo.",
    "REQUIRED_HANDLER_NOT_REGISTERED": "Windows no pudo mostrar la confirmación de emparejamiento.",
    "INVALID_CEREMONY_DATA": "Los datos de emparejamiento no son válidos.",
    "FAILED": "No se pudo emparejar.",
}

_UNPAIR = {
    "UNPAIRED": "Se olvidó el dispositivo.",
    "ALREADY_UNPAIRED": "Ya no estaba emparejado.",
    "ACCESS_DENIED": "Windows denegó olvidar el dispositivo.",
    "OPERATION_ALREADY_IN_PROGRESS": "Ya hay una operación en curso.",
    "FAILED": "No se pudo olvidar el dispositivo.",
}

_KIND = {"ble": "BLE", "classic": "Clásico", "dual": "Dual"}
_RADIO = {"on": "Encendido", "off": "Apagado", "disabled": "Desactivado", "unknown": "Sin estado"}
_ADDRESS_TYPE = {"public": "Dirección pública", "random": "Dirección aleatoria", "unspecified": "Dirección no indicada"}


def display_name(device: dict[str, Any]) -> str:
    return str(device.get("name") or "") or "Dispositivo sin nombre"


def signal_label(signal: int | None) -> str:
    if signal is None:
        return "—"
    return f"{signal} %"


def kind_label(device: dict[str, Any]) -> str:
    return _KIND.get(str(device.get("kind") or ""), "—")


def state_label(device: dict[str, Any]) -> str:
    if device.get("connected"):
        return "Conectado"
    if device.get("paired"):
        return "Emparejado"
    return "Visible"


def device_class(device: dict[str, Any]) -> str:
    label = class_label(device.get("cod_major"), device.get("cod_minor"))
    if label:
        return label
    return appearance_label(device.get("appearance"))


def services_label(device: dict[str, Any]) -> str:
    names = [service_name(item) for item in device.get("services") or []]
    if not names:
        return ""
    if len(names) <= 2:
        return " · ".join(names)
    return f"{names[0]} · {names[1]} · +{len(names) - 2}"


def detail_label(device: dict[str, Any]) -> str:
    company = company_name(device.get("company_id"))
    if company and not company.startswith("0x"):
        return company
    if device.get("present"):
        return "Visto en este barrido"
    if company:
        return company
    return ""


def is_input_device(device: dict[str, Any]) -> bool:
    if device.get("cod_major") == 5 or device.get("appearance") == 15:
        return True
    services = {str(item).lower() for item in device.get("services") or []}
    return bool(services & _HID_SERVICES)


def summary_text(radio: dict[str, Any] | None) -> str:
    if not radio:
        return "No se detectó un adaptador Bluetooth."
    title = radio.get("local_name") or radio.get("name") or "Bluetooth"
    lines = [f"{title} · {_RADIO.get(str(radio.get('state') or ''), 'Sin estado')}"]
    modes = []
    if radio.get("classic"):
        modes.append("clásico")
    if radio.get("ble"):
        modes.append("BLE")
    facts = []
    if radio.get("address"):
        facts.append(f"Dirección {radio['address']}")
    if modes:
        facts.append("Admite " + " y ".join(modes))
    if radio.get("discoverable") is True:
        facts.append("Visible para otros equipos")
    elif radio.get("discoverable") is False:
        facts.append("No visible")
    if radio.get("connectable") is True:
        facts.append("Acepta conexiones")
    if facts:
        lines.append(" · ".join(facts))
    return "\n".join(lines)


def detail_text(device: dict[str, Any] | None) -> str:
    if not device:
        return "Selecciona un dispositivo para ver su detalle y conectar o desconectar."
    lines = [
        display_name(device),
        str(device.get("address") or ""),
        " · ".join(
            part
            for part in (
                kind_label(device) if device.get("kind") else "",
                state_label(device),
                "Presente" if device.get("present") else "No presente",
            )
            if part and part != "—"
        ),
    ]
    signal = signal_label(device.get("signal"))
    if device.get("rssi") is not None:
        lines.append(f"Señal {device['rssi']} dBm ({signal})")
    elif signal != "—":
        lines.append(f"Señal {signal}")
    klass = device_class(device)
    if klass:
        lines.append(f"Clase: {klass}")
    company = company_name(device.get("company_id"))
    if company or device.get("manufacturer_hex"):
        extra = f" · {device['manufacturer_hex']}" if device.get("manufacturer_hex") else ""
        lines.append(f"Fabricante: {company or 'no indicado'}{extra}")
    names = [service_name(item) for item in device.get("services") or []]
    if names:
        lines.append("Servicios: " + ", ".join(names))
    category = str(device.get("category") or "")
    if category:
        lines.append(f"Categoría: {category}")
    address_type = _ADDRESS_TYPE.get(str(device.get("address_type") or ""))
    if address_type:
        lines.append(address_type)
    if device.get("tx_power") is not None:
        lines.append(f"Potencia de emisión: {device['tx_power']} dBm")
    if device.get("connectable") is True:
        lines.append("Anuncia que acepta conexión.")
    elif device.get("connectable") is False:
        lines.append("No anuncia conexión.")
    seen = _format_seen(device.get("last_seen"))
    if seen:
        lines.append(f"Última vez: {seen}")
    flags = int(device.get("flags") or 0)
    notes = []
    if flags & 0x4:
        notes.append("El anuncio indica que no ofrece Bluetooth clásico.")
    if flags & 0x18:
        notes.append("El anuncio indica modo dual, clásico y BLE.")
    if notes:
        lines.append(" ".join(notes))
    return "\n".join(line for line in lines if line)


def pairing_message(status: str) -> str:
    return _PAIRING.get(status, f"No se pudo emparejar ({status}).")


def unpair_message(status: str) -> str:
    return _UNPAIR.get(status, f"No se pudo olvidar el dispositivo ({status}).")


def filter_devices(devices: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    needle = query.strip().lower()
    if not needle:
        return list(devices)
    visible = []
    for device in devices:
        blob = " ".join(
            [
                display_name(device),
                str(device.get("address") or ""),
                kind_label(device),
                state_label(device),
                device_class(device),
                services_label(device),
                detail_label(device),
                company_name(device.get("company_id")),
                " ".join(service_name(item) for item in device.get("services") or []),
            ]
        ).lower()
        if needle in blob:
            visible.append(device)
    return visible


def sort_devices(devices: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    rows = list(devices)

    def signal_value(device: dict[str, Any]) -> int:
        signal = device.get("signal")
        return signal if isinstance(signal, int) else -1

    if key == "name":
        rows.sort(key=lambda device: (display_name(device).lower(), device.get("address") or ""))
    elif key == "kind":
        rows.sort(key=lambda device: (kind_label(device), display_name(device).lower()))
    elif key == "state":
        rows.sort(
            key=lambda device: (
                0 if device.get("connected") else 1 if device.get("paired") else 2,
                -signal_value(device),
                display_name(device).lower(),
            )
        )
    else:
        rows.sort(key=lambda device: (-signal_value(device), display_name(device).lower()))
    return rows


def _format_seen(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        moment = value
    else:
        try:
            moment = datetime.fromisoformat(str(value))
        except ValueError:
            return str(value)
    if moment.tzinfo is not None:
        moment = moment.astimezone()
    return moment.strftime("%d/%m/%Y %H:%M")
