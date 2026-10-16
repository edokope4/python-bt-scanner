"""Hilo con el bucle de Windows Runtime. La ventana no llama a WinRT directamente."""

from __future__ import annotations

import asyncio
import threading
from typing import Any


class Runtime:
    def __init__(self) -> None:
        self.sessions: dict[str, Any] = {}
        self.error = ""
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._scan_async = None
        self._connect = None
        self._disconnect = None
        self._pair = None
        self._unpair = None
        self.link: Any = None
        self._link_guard: asyncio.Lock | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="bt-runtime", daemon=True)
        self._thread.start()
        if not self._ready.wait(15):
            raise RuntimeError("No se pudo iniciar el acceso a Bluetooth.")
        if self.error:
            raise RuntimeError(self.error)

    def scan(self, *, refresh: bool = True) -> dict[str, Any]:
        if self._scan_async is None or self._loop is None:
            raise RuntimeError(self.error or "Bluetooth no está listo.")
        report = self.call(self._scan(refresh), timeout=50 if refresh else 25)
        return report

    def connect(self, device: dict[str, Any]) -> dict[str, Any]:
        return self.call(self._connect(device, self.sessions), timeout=30)

    def disconnect(self, device: dict[str, Any]) -> dict[str, Any]:
        return self.call(self._disconnect(device, self.sessions), timeout=30)

    def pair(self, device: dict[str, Any]) -> dict[str, Any]:
        return self.call(self._pair(device), timeout=90)

    def unpair(self, device: dict[str, Any]) -> dict[str, Any]:
        return self.call(self._unpair(device, self.sessions), timeout=40)

    def open_link(self, device: dict[str, Any], inbox: Any) -> dict[str, Any]:
        return self.call(self._open_link(device, inbox), timeout=40)

    def send_link(self, payload: bytes) -> dict[str, Any]:
        return self.call(self._send_link(payload), timeout=15)

    def close_link(self) -> None:
        if self._loop is None:
            return
        try:
            self.call(self._close_link(), timeout=8)
        except Exception:
            return

    def call(self, coro: Any, timeout: float) -> Any:
        if self._loop is None:
            raise RuntimeError(self.error or "Bluetooth no está listo.")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout)

    def stop(self) -> None:
        if self._loop is None:
            return
        future = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
        try:
            future.result(12)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)

    async def _scan(self, refresh: bool) -> dict[str, Any]:
        report = await self._scan_async(refresh=refresh)
        devices = report.get("devices") or []
        for device in devices:
            if device.get("address") in self.sessions:
                device["connected"] = True
        from bt_scanner.devices import recount

        report["counts"] = recount(devices)
        return report

    def _guard(self) -> asyncio.Lock:
        if self._link_guard is None:
            self._link_guard = asyncio.Lock()
        return self._link_guard

    async def _open_link(self, device: dict[str, Any], inbox: Any) -> dict[str, Any]:
        from bt_scanner.link import Link

        async with self._guard():
            await self._close_link_unlocked()
            link = Link(inbox)
            try:
                await link.open(device)
            except Exception as exc:
                await link.close()
                return {"ok": False, "message": str(exc)}
            self.link = link
            return {"ok": True, "message": link.description}

    async def _send_link(self, payload: bytes) -> dict[str, Any]:
        async with self._guard():
            link = self.link
            if link is None:
                return {"ok": False, "message": "No hay un canal abierto."}
            try:
                await link.send(payload)
            except Exception as exc:
                return {"ok": False, "message": str(exc)}
            return {"ok": True, "message": ""}

    async def _close_link(self) -> None:
        async with self._guard():
            await self._close_link_unlocked()

    async def _close_link_unlocked(self) -> None:
        link = self.link
        self.link = None
        if link is not None:
            await link.close()

    async def _shutdown(self) -> None:
        await self._close_link()
        await self._close_sessions()

    async def _close_sessions(self) -> None:
        from bt_scanner.actions import _close_session

        for held in list(self.sessions.values()):
            _close_session(held)
        self.sessions.clear()

    def _run(self) -> None:
        try:
            import winrt.windows.foundation  # noqa: F401
            from bt_scanner.actions import connect_device, disconnect_device, pair_device, unpair_device
            from bt_scanner.scanner import scan_async
        except Exception as exc:
            self.error = f"No se pudo cargar Bluetooth de Windows. Instala las dependencias con pip install -r requirements.txt.\n{exc}"
            self._ready.set()
            return
        self._scan_async = scan_async
        self._connect = connect_device
        self._disconnect = disconnect_device
        self._pair = pair_device
        self._unpair = unpair_device
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()
        self._loop.close()
