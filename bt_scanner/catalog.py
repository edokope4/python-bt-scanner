"""Nombres legibles de clases, servicios y fabricantes Bluetooth."""

from __future__ import annotations

COMPANIES = {
    0x0002: "Intel",
    0x0006: "Microsoft",
    0x000A: "CSR",
    0x000D: "Texas Instruments",
    0x000F: "Broadcom",
    0x004C: "Apple",
    0x0059: "Nordic Semiconductor",
    0x0075: "Samsung",
    0x0087: "Garmin",
    0x00D2: "Dialog Semiconductor",
    0x00E0: "Google",
    0x012D: "Sony",
    0x0131: "Cypress",
    0x0171: "Amazon",
}

# UUID de 16 bits, en minúsculas, sin el prefijo 0000.
SERVICES = {
    "1101": "Puerto serie",
    "1108": "Auriculares",
    "110a": "Audio (fuente)",
    "110b": "Audio (receptor)",
    "110c": "Control de audio (destino)",
    "110e": "Control de audio",
    "111e": "Manos libres",
    "111f": "Manos libres (puerta)",
    "1124": "HID",
    "1200": "PnP",
    "1800": "Acceso genérico",
    "1801": "Atributo genérico",
    "1804": "Potencia de emisión",
    "180a": "Información del dispositivo",
    "180d": "Ritmo cardíaco",
    "180f": "Batería",
    "1812": "HID",
    "1816": "Ciclismo",
    "1818": "Potencia de ciclismo",
    "181c": "Datos de usuario",
    "181d": "Báscula",
}

_MAJOR = {
    0: "Varios",
    1: "Ordenador",
    2: "Teléfono",
    3: "Red",
    4: "Audio",
    5: "Periférico",
    6: "Imagen",
    7: "Ponible",
    8: "Juguete",
    9: "Salud",
}

_COMPUTER = {1: "Sobremesa", 2: "Servidor", 3: "Portátil", 4: "De mano", 6: "Ponible", 7: "Tableta"}
_PHONE = {1: "Móvil", 2: "Inalámbrico", 3: "Teléfono", 4: "Módem", 5: "RDSI"}
_AUDIO = {
    1: "Auriculares",
    2: "Manos libres",
    4: "Micrófono",
    5: "Altavoz",
    6: "Auriculares",
    7: "Audio portátil",
    8: "Audio de coche",
    9: "Receptor",
    10: "Equipo de alta fidelidad",
    11: "Vídeo",
    12: "Cámara",
    13: "Videocámara",
    14: "Pantalla",
    15: "Pantalla con altavoz",
    16: "Videoconferencia",
    18: "Mando o juguete",
}
_WEARABLE = {1: "Reloj", 2: "Localizador", 3: "Chaqueta", 4: "Casco", 5: "Gafas"}
_HEALTH = {1: "Tensión", 2: "Termómetro", 3: "Báscula", 4: "Glucosa", 5: "Oxímetro", 6: "Pulso", 7: "Salud"}

_APPEARANCE = {
    1: "Teléfono",
    2: "Ordenador",
    3: "Reloj",
    4: "Reloj",
    5: "Pantalla",
    6: "Mando",
    7: "Gafas",
    8: "Etiqueta",
    9: "Llavero",
    10: "Reproductor",
    11: "Lector de códigos",
    12: "Termómetro",
    13: "Ritmo cardíaco",
    14: "Tensión",
    15: "Periférico",
    16: "Glucosa",
    17: "Actividad",
    18: "Ciclismo",
    49: "Oxímetro",
    50: "Báscula",
    81: "Deporte",
}

_BASE_UUID = "-0000-1000-8000-00805f9b34fb"


def short_uuid(value: str) -> str:
    text = value.strip().strip("{}").lower()
    if text.startswith("0000") and text.endswith(_BASE_UUID) and len(text) == 36:
        return text[4:8]
    if len(text) == 4:
        return text
    return text


def service_name(value: str) -> str:
    short = short_uuid(value)
    if short in SERVICES:
        return SERVICES[short]
    if len(short) == 4:
        return short.upper()
    return value.strip().strip("{}").upper()


def company_name(company_id: int | None) -> str:
    if company_id is None:
        return ""
    return COMPANIES.get(int(company_id), f"0x{int(company_id):04X}")


def class_label(major: int | None, minor: int | None) -> str:
    if major is None:
        return ""
    title = _MAJOR.get(int(major), "")
    if not title:
        return ""
    detail = _minor_label(int(major), int(minor) if minor is not None else None)
    if detail and detail != title:
        return f"{title} · {detail}"
    return title


def appearance_label(category: int | None) -> str:
    if category is None:
        return ""
    return _APPEARANCE.get(int(category), "")


def _minor_label(major: int, minor: int | None) -> str:
    if minor is None:
        return ""
    if major == 5:
        combo = minor & 0x30
        if combo == 0x10:
            return "Teclado"
        if combo == 0x20:
            return "Ratón"
        if combo == 0x30:
            return "Teclado y ratón"
    tables = {1: _COMPUTER, 2: _PHONE, 4: _AUDIO, 7: _WEARABLE, 9: _HEALTH}
    return tables.get(major, {}).get(minor, "")
