"""Texto de la consola: lo que se envía al Arduino y lo que llega de vuelta."""

from __future__ import annotations


def command_bytes(text: str, ending: str) -> bytes:
    """Codifica un comando. Si ya termina en salto de línea, no añade otro."""
    body = text.encode("utf-8")
    if ending == "none" or body.endswith(b"\n"):
        return body
    if ending == "crlf":
        return body + b"\r\n"
    return body + b"\n"


def decode_incoming(data: bytes) -> str:
    """Muestra el flujo como texto. Los bytes que no son UTF-8 quedan marcados."""
    text = data.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")
