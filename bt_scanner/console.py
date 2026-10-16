"""Ventana para escuchar respuestas y probar comandos de texto."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk
from typing import Any

from bt_scanner.transcript import command_bytes, decode_incoming
from bt_scanner.view import display_name

_LOG_LIMIT = 400


class ConsoleWindow(tk.Toplevel):
    def __init__(self, app: Any, device: dict[str, Any]) -> None:
        super().__init__(app)
        self.app = app
        self.device = device
        self.inbox: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.ending = tk.StringVar(value="lf")
        self._listening = False
        self._closing = False
        self._alive = True
        name = display_name(device)
        self.title(f"Consola · {name}")
        self.geometry("760x560")
        self.minsize(640, 420)
        self._build(name)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(100, self._poll)
        self.entry.focus_set()

    def start(self) -> None:
        threading.Thread(target=self._open_worker, daemon=True).start()

    def _build(self, name: str) -> None:
        style = ttk.Style(self)
        style.configure("ConsoleStatus.TLabel", font=("Segoe UI", 10))
        padding = ttk.Frame(self, padding=16)
        padding.pack(fill="both", expand=True)
        ttk.Label(padding, text="Consola Bluetooth", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            padding,
            text=f"{name} · {self.device.get('address') or ''}",
            foreground="#555555",
        ).pack(anchor="w", pady=(2, 8))
        self.status = ttk.Label(padding, text="Abriendo el canal…", style="ConsoleStatus.TLabel", wraplength=700, justify="left")
        self.status.pack(anchor="w")

        log_frame = ttk.Frame(padding)
        log_frame.pack(fill="both", expand=True, pady=(12, 8))
        self.log = tk.Text(
            log_frame,
            font=("Consolas", 11),
            wrap="word",
            relief="flat",
            background="#f7f7f5",
            padx=10,
            pady=8,
        )
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.log.tag_configure("sent", foreground="#1f4b99")
        self.log.tag_configure("status", foreground="#555555")
        self.log.tag_configure("error", foreground="#9b2c2c")
        self.log.bind("<Key>", self._ignore_typing)

        composer = ttk.Frame(padding)
        composer.pack(fill="x")
        self.entry = ttk.Entry(composer)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda _event: self._send())
        self.send_button = ttk.Button(composer, text="Enviar", command=self._send, state="disabled")
        self.send_button.pack(side="left", padx=(8, 0))

        options = ttk.Frame(padding)
        options.pack(fill="x", pady=(8, 0))
        ttk.Label(options, text="Al enviar").pack(side="left")
        for value, label in (("lf", "LF"), ("crlf", "CRLF"), ("none", "Sin salto")):
            ttk.Radiobutton(options, text=label, value=value, variable=self.ending).pack(side="left", padx=(8, 0))
        ttk.Button(options, text="Limpiar", command=self._clear).pack(side="right")
        ttk.Label(
            padding,
            text="El texto sale en UTF-8. Un sketch de Arduino suele leer hasta el salto de línea.",
            foreground="#555555",
        ).pack(anchor="w", pady=(8, 0))

    def abandon(self) -> None:
        self._alive = False
        self._closing = True
        self.destroy()

    def _open_worker(self) -> None:
        try:
            result = self.app.runtime.open_link(self.device, self.inbox)
        except Exception as exc:
            result = {"ok": False, "message": str(exc)}
        self.inbox.put(("ready", result))

    def _send(self) -> None:
        if not self._listening:
            return
        text = self.entry.get()
        ending = self.ending.get()
        if text == "" and ending == "none":
            return
        payload = command_bytes(text, ending)
        self.entry.delete(0, "end")
        shown = text if text else "(línea vacía)"
        self._append(f"→ {shown}\n", "sent")
        threading.Thread(target=self._send_worker, args=(payload,), daemon=True).start()

    def _send_worker(self, payload: bytes) -> None:
        try:
            result = self.app.runtime.send_link(payload)
        except Exception as exc:
            result = {"ok": False, "message": str(exc)}
        if not result.get("ok"):
            self.inbox.put(("error", result.get("message") or "No se pudo enviar."))

    def _poll(self) -> None:
        if not self._alive or not self.winfo_exists():
            return
        try:
            while True:
                kind, payload = self.inbox.get_nowait()
                if kind == "data":
                    self._append(decode_incoming(payload), "recv")
                elif kind == "ready":
                    self._on_ready(payload)
                elif kind == "status":
                    self._set_status(str(payload))
                    self._append(str(payload) + "\n", "status")
                elif kind == "error":
                    self._append(str(payload) + "\n", "error")
                elif kind == "closed":
                    was_listening = self._listening
                    self._listening = False
                    self._sync_send()
                    current = self.status.cget("text").lower()
                    if was_listening and "cerr" not in current and "cort" not in current:
                        self._set_status("Canal cerrado.")
        except queue.Empty:
            pass
        if self._alive and self.winfo_exists():
            self.after(100, self._poll)

    def _on_ready(self, result: dict[str, Any]) -> None:
        self._listening = bool(result.get("ok"))
        message = str(result.get("message") or ("Escuchando." if self._listening else "No se abrió el canal."))
        self._set_status(message)
        self._append(message + "\n", "status" if self._listening else "error")
        self._sync_send()

    def _set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def _append(self, text: str, tag: str) -> None:
        self.log.insert("end", text, tag)
        self._trim()
        self.log.see("end")

    def _trim(self) -> None:
        lines = int(float(self.log.index("end-1c")))
        if lines > _LOG_LIMIT:
            self.log.delete("1.0", f"{lines - _LOG_LIMIT}.0")

    def _clear(self) -> None:
        self.log.delete("1.0", "end")

    def _sync_send(self) -> None:
        self.send_button.configure(state="normal" if self._listening else "disabled")
        self.entry.configure(state="normal" if self._listening else "disabled")

    def _ignore_typing(self, event: tk.Event[tk.Text]) -> str | None:
        if event.keysym in {
            "Left",
            "Right",
            "Up",
            "Down",
            "Home",
            "End",
            "Prior",
            "Next",
            "Shift_L",
            "Shift_R",
            "Control_L",
            "Control_R",
        }:
            return None
        if event.state & 0x4 and event.keysym.lower() in {"c", "a", "insert"}:
            if event.keysym.lower() == "a":
                self.log.tag_add("sel", "1.0", "end")
                return "break"
            return None
        return "break"

    def _close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._listening = False
        self._sync_send()
        self._set_status("Cerrando el canal…")
        threading.Thread(target=self._close_worker, daemon=True).start()

    def _close_worker(self) -> None:
        try:
            if getattr(self.app, "_console", None) is self:
                self.app.runtime.close_link()
        except Exception:
            pass
        try:
            self.after(0, self._finish_close)
        except tk.TclError:
            return

    def _finish_close(self) -> None:
        self._alive = False
        if getattr(self.app, "_console", None) is self:
            self.app._console = None
        self.destroy()
