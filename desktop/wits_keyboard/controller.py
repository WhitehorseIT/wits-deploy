"""Multi-board orchestration above individual BLE sessions."""

from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from . import protocol
from .session import BoardSession
from .auto_connect import AutoConnector

logger = logging.getLogger(__name__)

ControllerEvent = Callable[[str, str, dict[str, Any]], None]


@dataclass(slots=True)
class DiscoveredBoard:
    address: str
    name: str


class KeyboardController:
    def __init__(self, event_callback: ControllerEvent, *, pairing_callback: Any = None) -> None:
        self.event_callback = event_callback
        self.pairing_callback = pairing_callback
        self.scan_lock = asyncio.Lock()
        self.radio_lock = asyncio.Lock()
        self.devices: dict[str, Any] = {}
        self.known_devices: dict[str, DiscoveredBoard] = {}
        self.sessions: dict[str, BoardSession] = {}
        self.connect_tasks: dict[str, asyncio.Task[None]] = {}
        self.repair_tasks: dict[str, asyncio.Task[None]] = {}
        self.reconnector = AutoConnector(self)

    async def set_auto_connect(self, address: str, enabled: bool) -> None:
        if address not in self.known_devices:
            raise RuntimeError("Save or scan this board before enabling Auto-connect")
        self.reconnector.configure(address, enabled)

    def _emit(self, address: str, event: str, **details: Any) -> None:
        self.event_callback(address, event, details)

    async def scan(self, timeout: float = 6.0) -> list[DiscoveredBoard]:
        try:
            from bleak import BleakScanner
        except ImportError as error:
            raise RuntimeError(
                "Bleak is not installed; run pip install -r requirements.txt"
            ) from error

        logger.info("BLE scan begin timeout=%.1f service=%s", timeout, protocol.SERVICE_UUID)
        try:
            async with self.radio_lock, self.scan_lock:
                found = await BleakScanner.discover(
                    timeout=timeout, service_uuids=[protocol.SERVICE_UUID]
                )
        except Exception:
            logger.exception("BLE scan failed")
            raise
        logger.info("BLE scan returned %d matching device(s)", len(found))
        boards: list[DiscoveredBoard] = []
        for device in found:
            name = device.name or "WITS Deploy"
            self.devices[device.address] = device
            boards.append(DiscoveredBoard(device.address, name))
            self.known_devices[device.address] = boards[-1]
            logger.info("Discovered board address=%s name=%s", device.address, name)
        boards.sort(key=lambda board: (board.name.casefold(), board.address))
        return boards

    async def connect(self, address: str, *, allow_pairing: bool = True) -> None:
        logger.info("Controller connect address=%s", address)
        if address not in self.devices and address not in self.known_devices:
            raise RuntimeError("scan for this board before connecting")
        if allow_pairing:
            self.reconnector.resume(address)
        task = self.connect_tasks.get(address)
        if task is None or task.done():
            task = asyncio.create_task(
                self._connect(address, allow_pairing=allow_pairing), name=f"connect-{address}"
            )
            self.connect_tasks[address] = task
        else:
            logger.info("Joining existing connection attempt address=%s", address)
        try:
            await task
        finally:
            if task.done() and self.connect_tasks.get(address) is task:
                self.connect_tasks.pop(address, None)

    async def _resolve_device(self, address: str) -> Any:
        if address in self.devices:
            return self.devices[address]
        self._emit(address, "progress", message="Looking up saved board…")
        device = None
        if sys.platform == "linux":
            try:
                from .linux_diagnostics import cached_linux_device

                device = await cached_linux_device(address)
            except Exception as error:
                logger.info("Saved board lookup unavailable address=%s error=%s", address, error)
        if device is None:
            from bleak import BleakScanner

            self._emit(address, "progress", message="Searching for saved board; check power and HID mode…")
            async with self.scan_lock:
                device = await BleakScanner.find_device_by_address(address, timeout=8.0)
        if device is None:
            raise RuntimeError(
                "Saved board is not available. Check it is powered, nearby and in HID mode. "
                "Open the pairing window only for a first pairing or to replace a cleared bond."
            )
        self.devices[address] = device
        return device

    async def _connect(self, address: str, *, allow_pairing: bool = True) -> None:
        async with self.radio_lock:
            device = await self._resolve_device(address)
            session = self.sessions.get(address)
            if session is None:
                session = BoardSession(device, self.event_callback, pairing_callback=self.pairing_callback)
                self.sessions[address] = session
            else:
                session.device = device
            await session.connect(allow_pairing=allow_pairing)

    async def repair(self, address: str, timeout: float = 12.0) -> None:
        """Forget a stale OS bond, rediscover the board, and pair again."""
        self.reconnector.pause(address)
        task = self.repair_tasks.get(address)
        if task is None or task.done():
            task = asyncio.create_task(self._repair(address, timeout), name=f"repair-{address}")
            self.repair_tasks[address] = task
        try:
            await task
        finally:
            if task.done() and self.repair_tasks.get(address) is task:
                self.repair_tasks.pop(address, None)

    async def _repair(self, address: str, timeout: float) -> None:
        if address not in self.devices and address not in self.known_devices:
            raise RuntimeError("scan for this board before re-pairing")

        logger.info("Repair pairing begin address=%s", address)
        existing_task = self.connect_tasks.pop(address, None)
        if existing_task is not None and not existing_task.done():
            logger.info("Canceling existing connection before repair address=%s", address)
            existing_task.cancel()
            await asyncio.gather(existing_task, return_exceptions=True)

        async with self.radio_lock:
            await self._resolve_device(address)
            session = self.sessions.get(address)
            if session is None:
                session = BoardSession(self.devices[address], self.event_callback,
                                       pairing_callback=self.pairing_callback)
            await session.forget_bond()
            self.sessions.pop(address, None)

        boards = await self.scan(timeout=timeout)
        if not any(board.address == address for board in boards):
            raise RuntimeError(
                "board was forgotten but not rediscovered; open its pairing window and scan again"
            )

        logger.info("Repair pairing rediscovered address=%s", address)
        await self.connect(address)
        logger.info("Repair pairing complete address=%s", address)

    async def disconnect(self, address: str) -> None:
        logger.info("Controller disconnect address=%s", address)
        self.reconnector.pause(address)
        task = self.repair_tasks.get(address) or self.connect_tasks.get(address)
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        session = self.sessions.get(address)
        if session is not None:
            await session.disconnect()

    async def disconnect_all(self) -> None:
        logger.info("Disconnect all sessions count=%d", len(self.sessions))
        await self.reconnector.stop()
        for task in tuple(self.repair_tasks.values()):
            if not task.done():
                task.cancel()
        if self.repair_tasks:
            await asyncio.gather(*self.repair_tasks.values(), return_exceptions=True)
        self.repair_tasks.clear()
        for task in tuple(self.connect_tasks.values()):
            if not task.done():
                task.cancel()
        if self.connect_tasks:
            await asyncio.gather(*self.connect_tasks.values(), return_exceptions=True)
        self.connect_tasks.clear()
        await asyncio.gather(
            *(session.disconnect() for session in self.sessions.values()),
            return_exceptions=True,
        )

    def _connected(self, address: str) -> BoardSession:
        session = self.sessions.get(address)
        if session is None or not session.state.connected:
            raise RuntimeError("board is not connected")
        return session

    async def ping(self, address: str) -> None:
        logger.info("Controller ping address=%s", address)
        await self._connected(address).ping()

    async def identify(self, address: str, label: str = "") -> None:
        logger.info("Controller identify address=%s", address)
        await self._connected(address).identify(label)

    async def read_info(self, address: str) -> None:
        await self._connected(address).read_info()

    async def storage_mode(self, address: str, allow_writes: bool) -> None:
        await self._connected(address).storage_mode(allow_writes)

    async def update_firmware(self, address, image, progress, cancelled=None):
        async with self.radio_lock:
            await self._connected(address).update_firmware(image, progress, cancelled)

    async def key_action(self, address: str, key_code: int, modifiers: int) -> None:
        logger.info(
            "Controller key action address=%s key_code=%#04x modifiers=%#04x",
            address,
            key_code,
            modifiers,
        )
        await self._connected(address).key_action(key_code, modifiers)

    async def send_text_many(self, addresses: Iterable[str], text: str,
                             key_interval_ms: int = protocol.DEFAULT_KEY_INTERVAL_MS) -> None:
        addresses = tuple(addresses)
        logger.info(
            "Multi-send begin targets=%s bytes=%d content=omitted",
            addresses,
            len(text.encode("ascii")),
        )
        async def send_one(address: str) -> None:
            try:
                await self._connected(address).send_text(text, key_interval_ms)
                self._emit(address, "operation", success=True, message="Text accepted")
            except Exception as error:
                # Deliberately never retry: the target may already have received
                # part of the text when a transport error becomes visible.
                self._emit(address, "operation", success=False, message=str(error))
                logger.exception("Text send failed address=%s", address)

        await asyncio.gather(*(send_one(address) for address in addresses))

    async def stop_many(self, addresses: Iterable[str]) -> None:
        addresses = tuple(addresses)
        logger.info("Stop many targets=%s", addresses)
        async def stop_one(address: str) -> None:
            try:
                await self._connected(address).stop()
                self._emit(address, "operation", success=True, message="Stopped")
            except Exception as error:
                self._emit(address, "operation", success=False, message=str(error))
                logger.exception("Stop failed address=%s", address)

        await asyncio.gather(*(stop_one(address) for address in addresses))

    async def stop_all(self) -> None:
        await self.stop_many(
            address
            for address, session in self.sessions.items()
            if session.state.connected
        )
