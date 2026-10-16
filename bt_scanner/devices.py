"""Mezcla de los datos que llegan de anuncios, emparejamiento y la API clásica."""

from __future__ import annotations

import re
from typing import Any

_ADDRESS = re.compile(r"^[0-9A-F]{2}(?::[0-9A-F]{2}){5}$")


def format_address(value: int) -> str:
    text = f"{value & 0xFFFFFFFFFFFF:012X}"
    return ":".join(text[index : index + 2] for index in range(0, 12, 2))


def parse_address(value: str) -> str:
    text = str(value or "").strip().replace("-", ":").upper()
    if _ADDRESS.match(text):
        return text
    compact = text.replace(":", "")
    if len(compact) == 12 and all(char in "0123456789ABCDEF" for char in compact):
        return ":".join(compact[index : index + 2] for index in range(0, 12, 2))
    return ""


def address_int(value: str) -> int:
    return int(parse_address(value).replace(":", ""), 16)


def signal_percent(rssi: int | None) -> int | None:
    """Pasa dBm a un porcentaje. -40 dBm o más es 100 %; -100 dBm o menos es 0 %."""
    if rssi is None:
        return None
    clamped = max(-100, min(-40, int(rssi)))
    return round((clamped + 100) * 100 / 60)


def normalize_uuid(value: str) -> str:
    text = str(value or "").strip().strip("{}").lower()
    if len(text) == 4 and all(char in "0123456789abcdef" for char in text):
        return f"0000{text}-0000-1000-8000-00805f9b34fb"
    return text


def clean_name(name: str, address: str) -> str:
    text = " ".join(str(name or "").split())
    if not text:
        return ""
    folded = text.replace(":", "").replace("-", "").upper()
    if folded == address.replace(":", ""):
        return ""
    return text


def combine_kind(left: str, right: str) -> str:
    values = {item for item in (left, right) if item}
    if "dual" in values or values == {"ble", "classic"}:
        return "dual"
    if values:
        return next(iter(values))
    return ""


def new_device(address: str) -> dict[str, Any]:
    return {
        "address": address,
        "name": "",
        "kind": "",
        "rssi": None,
        "signal": None,
        "paired": False,
        "connected": False,
        "present": False,
        "can_pair": False,
        "connectable": None,
        "device_id": "",
        "device_ids": [],
        "cod_major": None,
        "cod_minor": None,
        "appearance": None,
        "company_id": None,
        "manufacturer_hex": "",
        "services": [],
        "tx_power": None,
        "address_type": "",
        "last_seen": "",
        "category": "",
        "flags": 0,
    }


def apply_patch(device: dict[str, Any], patch: dict[str, Any]) -> None:
    address = device["address"]
    name = clean_name(str(patch.get("name") or ""), address)
    if name:
        device["name"] = name
    kind = combine_kind(str(device.get("kind") or ""), str(patch.get("kind") or ""))
    if kind:
        device["kind"] = kind
    services = [normalize_uuid(item) for item in patch.get("services") or [] if item]
    if services:
        current = list(device.get("services") or [])
        for service in services:
            if service not in current:
                current.append(service)
        device["services"] = current
    if patch.get("manufacturer_hex"):
        device["manufacturer_hex"] = str(patch["manufacturer_hex"])
    if patch.get("device_id"):
        device_id = str(patch["device_id"])
        ids = list(device.get("device_ids") or [])
        if device_id not in ids:
            ids.append(device_id)
        device["device_ids"] = ids
        device["device_id"] = device_id
    for key in (
        "rssi",
        "cod_major",
        "cod_minor",
        "appearance",
        "company_id",
        "tx_power",
        "address_type",
        "last_seen",
        "category",
    ):
        if key in patch and patch[key] not in (None, ""):
            device[key] = patch[key]
    for key in ("paired", "connected", "can_pair"):
        if key in patch and patch[key] is not None:
            device[key] = bool(patch[key])
    if "present" in patch and patch["present"] is not None:
        device["present"] = bool(device.get("present")) or bool(patch["present"])
    if "connectable" in patch and patch["connectable"] is not None:
        device["connectable"] = bool(patch["connectable"])
    if "flags" in patch and patch["flags"]:
        device["flags"] = int(device.get("flags") or 0) | int(patch["flags"])
    if device.get("rssi") is not None:
        device["signal"] = signal_percent(int(device["rssi"]))


def merge_devices(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered: dict[str, dict[str, Any]] = {}
    for record in records:
        address = parse_address(str(record.get("address") or ""))
        if not address:
            continue
        current = ordered.get(address)
        if current is None:
            current = new_device(address)
            ordered[address] = current
        apply_patch(current, record)
    return list(ordered.values())


def recount(devices: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "devices": len(devices),
        "paired": sum(1 for device in devices if device.get("paired")),
        "connected": sum(1 for device in devices if device.get("connected")),
    }
