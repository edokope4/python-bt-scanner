"""Ventana de escritorio del escáner Bluetooth."""

from __future__ import annotations

import ctypes
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Any

from bt_scanner import __version__
from bt_scanner.console import ConsoleWindow
from bt_scanner.runtime import Runtime
from bt_scanner.view import (
    detail_label,
    detail_text,
    device_class,
    display_name,
    filter_devices,
    is_input_device,
    kind_label,
    services_label,
    signal_label,
    sort_devices,
    state_label,
    summary_text,
)

_COLUMNS = (
    ("state", "Estado", 110, False),
    ("signal", "Señal", 70, False),
    ("name", "Nombre", 220, True),
    ("address", "Dirección", 160, False),
    ("kind", "Tipo", 90, False),
    ("klass", "Clase", 170, False),
    ("services", "Servicios", 240, True),
    ("detail", "Detalle", 170, True),
)


def main() -> int:
    _enable_dpi()
    try:
        app = App()
    except (tk.TclError, RuntimeError, OSError) as exc:
        return _report_startup_error(exc)
    app.mainloop()
    return 0


class App(tk.Tk):
    def __init__(self, *, start_scan: bool = True) -> None:
        super().__init__()
        self.title("Escáner Bluetooth")
        self.geometry("1280x780")
        self.minsize(960, 620)
        self.runtime = Runtime()
        self.runtime.start()
        self._report: dict[str, Any] | None = None
        self._devices: dict[str, dict[str, Any]] = {}
        self._busy = False
        self._auto_job: str | None = None
        self._console: ConsoleWindow | None = None
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._close)
        if start_scan:
            self.after(200, lambda: self.start_scan(refresh=True))

    def _build(self) -> None:
        style = ttk.Style(self)
        style.configure(".", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Lead.TLabel", font=("Segoe UI", 13))
        style.configure("Muted.TLabel", foreground="#555555")
        style.configure("Warn.TLabel", foreground="#8a4b12")
        style.configure("Error.TLabel", foreground="#9b2c2c")
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=28)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.configure("Scan.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 6))

        padding = ttk.Frame(self, padding=16)
        padding.pack(fill="both", expand=True)

        header = ttk.Frame(padding)
        header.pack(fill="x")
        ttk.Label(header, text="Escáner Bluetooth", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Muestra los dispositivos cercanos y los emparejados con este equipo. Selecciona una fila para ver el detalle, conectar, desconectar o abrir la consola.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 10))
        self.summary = ttk.Label(header, text="Preparando el primer barrido…", style="Lead.TLabel", justify="left")
        self.summary.pack(anchor="w")

        self.message = ttk.Label(padding, text="", wraplength=1180, justify="left")
        self.message.pack(anchor="w", fill="x", pady=(8, 0))

        toolbar = ttk.Frame(padding)
        toolbar.pack(fill="x", pady=(12, 8))
        ttk.Label(toolbar, text="Buscar").pack(side="left")
        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *_args: self._fill_tree())
        ttk.Entry(toolbar, textvariable=self.query, width=28).pack(side="left", padx=(6, 14))

        ttk.Label(toolbar, text="Orden").pack(side="left")
        self.sort_key = tk.StringVar(value="Señal")
        sort_box = ttk.Combobox(
            toolbar,
            textvariable=self.sort_key,
            state="readonly",
            width=12,
            values=("Señal", "Nombre", "Tipo", "Estado"),
        )
        sort_box.pack(side="left", padx=(6, 14))
        sort_box.bind("<<ComboboxSelected>>", lambda _event: self._fill_tree())

        self.auto = tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar, text="Repetir cada 15 s", variable=self.auto, command=self._toggle_auto).pack(
            side="left", padx=(0, 10)
        )
        self.scan_button = ttk.Button(toolbar, text="Escanear", style="Scan.TButton", command=lambda: self.start_scan(True))
        self.scan_button.pack(side="left")
        self.count_label = ttk.Label(toolbar, text="", style="Muted.TLabel")
        self.count_label.pack(side="right")

        table = ttk.Frame(padding)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=[column[0] for column in _COLUMNS], show="headings", selectmode="browse")
        for key, title, width, stretch in _COLUMNS:
            self.tree.heading(key, text=title, command=lambda column=key: self._sort_by(column))
            self.tree.column(key, width=width, minwidth=60, stretch=stretch, anchor="w")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.tag_configure("connected", background="#e7f0d4")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._show_selection())

        actions = ttk.Frame(padding)
        actions.pack(fill="x", pady=(8, 0))
        self.connect_button = ttk.Button(actions, text="Conectar", command=self._connect, state="disabled")
        self.disconnect_button = ttk.Button(actions, text="Desconectar", command=self._disconnect, state="disabled")
        self.pair_button = ttk.Button(actions, text="Emparejar", command=self._pair, state="disabled")
        self.forget_button = ttk.Button(actions, text="Olvidar", command=self._forget, state="disabled")
        self.console_button = ttk.Button(actions, text="Consola", command=self._open_console, state="disabled")
        for button in (
            self.connect_button,
            self.disconnect_button,
            self.pair_button,
            self.forget_button,
            self.console_button,
        ):
            button.pack(side="left", padx=(0, 8))
        self.action_status = ttk.Label(actions, text="", style="Muted.TLabel")
        self.action_status.pack(side="right")

        self.detail = ttk.Label(
            padding,
            text="Selecciona un dispositivo para ver su detalle y conectar o desconectar.",
            wraplength=1180,
            justify="left",
        )
        self.detail.pack(anchor="w", fill="x", pady=(8, 0))

        self.status = tk.StringVar(value=f"Versión {__version__}")
        ttk.Label(padding, textvariable=self.status, style="Muted.TLabel").pack(anchor="w", pady=(8, 0))

    def start_scan(self, refresh: bool = True) -> None:
        if self._busy:
            return
        self._busy = True
        self.scan_button.configure(state="disabled", text="Escaneando…" if refresh else "Actualizando…")
        self.status.set("Buscando dispositivos cercanos…" if refresh else "Actualizando el estado…")
        self._sync_buttons()
        threading.Thread(target=self._scan_worker, args=(refresh,), daemon=True).start()

    def _scan_worker(self, refresh: bool) -> None:
        try:
            report = self.runtime.scan(refresh=refresh)
        except Exception as exc:
            report = {
                "ok": False,
                "error": str(exc),
                "warnings": [],
                "radio": None,
                "devices": [],
                "counts": {},
                "version": __version__,
            }
        self._post(lambda report=report: self._apply(report))

    def _apply(self, report: dict[str, Any]) -> None:
        if not self.winfo_exists():
            return
        self._busy = False
        self.scan_button.configure(state="normal", text="Escanear")
        self._report = report
        devices = report.get("devices") or []
        self._devices = {device["address"]: device for device in devices}
        self.summary.configure(text=summary_text(report.get("radio")))
        self._show_messages(report)
        self._fill_tree()
        self._show_status(report)
        if self.auto.get():
            self._schedule_auto()

    def _show_messages(self, report: dict[str, Any]) -> None:
        lines: list[str] = []
        if report.get("error"):
            lines.append(str(report["error"]))
        elif not report.get("ok", True):
            lines.append("No se pudo leer el Bluetooth.")
        lines.extend(str(warning) for warning in report.get("warnings") or [] if warning)
        self.message.configure(text="\n".join(lines), style="Error.TLabel" if report.get("error") else "Warn.TLabel")

    def _fill_tree(self) -> None:
        report = self._report or {}
        selected = self._selected_address()
        devices = filter_devices(list(self._devices.values()), self.query.get())
        devices = sort_devices(devices, self._current_sort())
        self.tree.delete(*self.tree.get_children())
        for device in devices:
            tags = ["connected"] if device.get("connected") else []
            self.tree.insert(
                "",
                "end",
                iid=device["address"],
                values=(
                    state_label(device),
                    signal_label(device.get("signal")),
                    display_name(device),
                    device.get("address") or "",
                    kind_label(device),
                    device_class(device),
                    services_label(device),
                    detail_label(device),
                ),
                tags=tags,
            )
        total = len(self._devices)
        paired = sum(1 for device in self._devices.values() if device.get("paired"))
        connected = sum(1 for device in self._devices.values() if device.get("connected"))
        if not report:
            self.count_label.configure(text="")
        elif len(devices) == total:
            self.count_label.configure(text=f"{total} dispositivos · {paired} emparejados · {connected} conectados")
        else:
            self.count_label.configure(text=f"{len(devices)} de {total}")
        if report and not devices:
            empty = "Ningún dispositivo coincide con el filtro." if total else "No hay dispositivos visibles en este momento."
            self.tree.insert("", "end", iid="empty", values=("", "", empty, "", "", "", "", ""))
        if selected and self.tree.exists(selected):
            self.tree.selection_set(selected)
            self.tree.see(selected)
        self._show_selection()

    def _show_selection(self) -> None:
        self.detail.configure(text=detail_text(self._selected_device()))
        self._sync_buttons()

    def _show_status(self, report: dict[str, Any]) -> None:
        scanned_at = report.get("scanned_at")
        when = ""
        if scanned_at:
            try:
                when = datetime.fromisoformat(str(scanned_at)).strftime("%H:%M:%S")
            except ValueError:
                when = str(scanned_at)
        duration = report.get("duration_ms")
        seconds = f"{duration / 1000:.1f} s".replace(".", ",") if isinstance(duration, int) else ""
        parts = [
            f"Versión {report.get('version') or __version__}",
            f"Último barrido: {when}" if when else "",
            seconds,
        ]
        self.status.set(" · ".join(part for part in parts if part))

    def _connect(self) -> None:
        device = self._selected_device()
        if device is None or device.get("connected"):
            return
        self._run_action("Conectando…", lambda snapshot=_snapshot(device): self.runtime.connect(snapshot))

    def _disconnect(self) -> None:
        device = self._selected_device()
        if device is None or not device.get("connected"):
            return
        if is_input_device(device):
            question = "Si desconectas un teclado o un ratón Bluetooth puedes quedarte sin control hasta volver a conectarlo.\n\n¿Desconectar?"
        else:
            question = f"¿Desconectar {display_name(device)}?"
        if not messagebox.askyesno("Desconectar", question, parent=self):
            return
        snapshot = _snapshot(device)

        def work() -> dict[str, Any]:
            console = self._console
            if console is not None and console.device.get("address") == snapshot.get("address"):
                self.runtime.close_link()
            return self.runtime.disconnect(snapshot)

        self._run_action("Desconectando…", work)

    def _pair(self) -> None:
        device = self._selected_device()
        if device is None or device.get("paired"):
            return
        self._run_action(
            "Emparejando… Windows puede pedir una confirmación o un PIN.",
            lambda snapshot=_snapshot(device): self.runtime.pair(snapshot),
        )

    def _forget(self) -> None:
        device = self._selected_device()
        if device is None or not device.get("paired"):
            return
        extra = ""
        if is_input_device(device):
            extra = "\n\nSi es un teclado o un ratón, tendrás que emparejarlo otra vez para usarlo."
        if not messagebox.askyesno("Olvidar", f"¿Olvidar {display_name(device)}?{extra}", parent=self):
            return
        self._run_action("Olvidando el dispositivo…", lambda snapshot=_snapshot(device): self.runtime.unpair(snapshot))

    def _open_console(self) -> None:
        device = self._selected_device()
        if device is None or self._busy:
            return
        snapshot = _snapshot(device)
        existing = self._console
        if existing is not None and existing.winfo_exists() and not existing._closing:
            if existing.device.get("address") == snapshot.get("address"):
                existing.lift()
                existing.focus_force()
                return
            existing.abandon()
        window = ConsoleWindow(self, snapshot)
        self._console = window
        window.start()

    def _run_action(self, pending: str, func: Any) -> None:
        if self._busy:
            return
        self._busy = True
        self.scan_button.configure(state="disabled")
        self._sync_buttons()
        self.action_status.configure(text=pending, style="Muted.TLabel")
        threading.Thread(target=self._action_worker, args=(func,), daemon=True).start()

    def _action_worker(self, func: Any) -> None:
        try:
            result = func()
        except Exception as exc:
            result = {"ok": False, "message": str(exc)}
        self._post(lambda result=result: self._apply_action(result))

    def _post(self, callback: Any) -> None:
        try:
            if self.winfo_exists():
                self.after(0, callback)
        except tk.TclError:
            return

    def _apply_action(self, result: dict[str, Any]) -> None:
        if not self.winfo_exists():
            return
        self._busy = False
        self.scan_button.configure(state="normal", text="Escanear")
        address = result.get("address")
        device = self._devices.get(address) if address else None
        if device is not None:
            for key in ("paired", "connected"):
                if key in result and result[key] is not None:
                    device[key] = result[key]
        self.action_status.configure(
            text=str(result.get("message") or ""),
            style="Error.TLabel" if result and not result.get("ok", True) else "Muted.TLabel",
        )
        self._fill_tree()

    def _selected_address(self) -> str:
        selected = self.tree.selection() if hasattr(self, "tree") else ()
        return selected[0] if selected else ""

    def _selected_device(self) -> dict[str, Any] | None:
        return self._devices.get(self._selected_address())

    def _sync_buttons(self) -> None:
        device = None if self._busy else self._selected_device()
        paired = bool(device and device.get("paired"))
        connected = bool(device and device.get("connected"))
        self.connect_button.configure(state="normal" if device and not connected else "disabled")
        self.disconnect_button.configure(state="normal" if connected else "disabled")
        self.pair_button.configure(state="normal" if device and not paired else "disabled")
        self.forget_button.configure(state="normal" if paired else "disabled")
        self.console_button.configure(state="normal" if device else "disabled")

    def _current_sort(self) -> str:
        labels = {"Señal": "signal", "Nombre": "name", "Tipo": "kind", "Estado": "state"}
        return labels.get(self.sort_key.get(), "signal")

    def _sort_by(self, column: str) -> None:
        labels = {"signal": "Señal", "name": "Nombre", "kind": "Tipo", "state": "Estado"}
        if column not in labels:
            return
        self.sort_key.set(labels[column])
        self._fill_tree()

    def _toggle_auto(self) -> None:
        if self._auto_job is not None:
            self.after_cancel(self._auto_job)
            self._auto_job = None
        if self.auto.get():
            self.start_scan(refresh=True)
            self._schedule_auto()

    def _schedule_auto(self) -> None:
        if self._auto_job is not None:
            self.after_cancel(self._auto_job)
        if self.auto.get() and self.winfo_exists():
            self._auto_job = self.after(15000, self._auto_tick)

    def _auto_tick(self) -> None:
        self._auto_job = None
        if not self.auto.get():
            return
        if self._busy:
            self._schedule_auto()
            return
        self.start_scan(refresh=True)

    def _close(self) -> None:
        if self._auto_job is not None:
            self.after_cancel(self._auto_job)
            self._auto_job = None
        try:
            self.runtime.stop()
        except Exception:
            pass
        self.destroy()


def _snapshot(device: dict[str, Any]) -> dict[str, Any]:
    copy = dict(device)
    copy["services"] = list(device.get("services") or [])
    copy["device_ids"] = list(device.get("device_ids") or [])
    return copy


def _enable_dpi() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            return


def _report_startup_error(exc: BaseException) -> int:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("Escáner Bluetooth", f"No se pudo abrir la ventana:\n{exc}")
    root.destroy()
    return 1
