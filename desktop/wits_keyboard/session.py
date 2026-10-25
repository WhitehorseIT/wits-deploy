"""One authenticated BLE session to a WITS Deploy board."""

from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import asdict, dataclass
from typing import Any, Callable

from . import protocol
from .logging_config import safe_error
from .bonding import PairingRequired, has_saved_bond

logger = logging.getLogger(__name__)

EventCallback = Callable[[str, str, dict[str, Any]], None]


class BoardError(RuntimeError):
    pass


class BoardRejectedError(BoardError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(slots=True)
class BoardState:
    connected: bool = False
    authenticated: bool = False
    armed: bool = False
    typing: bool = False
    last_error: str = ""


class BoardSession:
    def __init__(
        self,
        device: Any,
        event_callback: EventCallback,
        *,
        client_factory: Any | None = None,
        pairing_callback: Any = None,
    ) -> None:
        self.device = device
        self.address = device.address
        self.name = device.name or "WITS Deploy"
        self.event_callback = event_callback
        self.client_factory = client_factory
        self.pairing_callback = pairing_callback
        self.client: Any | None = None
        self.state = BoardState()
        self.sequences = protocol.SequenceCounter()
        self.pending: dict[int, asyncio.Future[protocol.StatusFrame]] = {}
        self.request_lock = asyncio.Lock()
        self.connecting = False
        self.key_interval_ms = protocol.DEFAULT_KEY_INTERVAL_MS
        self.linux_diagnostics: Any = None
        logger.debug("Session created address=%s name=%s", self.address, self.name)

    def _emit(self, event: str, **details: Any) -> None:
        self.event_callback(self.address, event, details)

    def _emit_state(self) -> None:
        logger.debug("State address=%s %s", self.address, asdict(self.state))
        self._emit("state", name=self.name, **asdict(self.state))

    async def connect(self, *, allow_pairing: bool = True) -> None:
        if self.state.connected:
            logger.debug("Connect skipped; already connected address=%s", self.address)
            return
        if self.connecting:
            raise BoardError("connection is already in progress")
        if self.client_factory is None:
            try:
                from bleak import BleakClient
            except ImportError as error:
                raise BoardError(
                    "Bleak is not installed; run pip install -r requirements.txt"
                ) from error
            self.client_factory = BleakClient

        self.connecting = True
        self._emit("progress", message="Pairing and connecting…")
        app_pairing = sys.platform == "linux" and self.pairing_callback is not None
        logger.info("Connect begin address=%s name=%s pairing=%s timeout=90", self.address,
                    self.name, "app-agent" if app_pairing else "OS")
        discovery = None
        try:
            if not allow_pairing and not await has_saved_bond(self.device):
                raise PairingRequired("Automatic reconnect requires an existing OS bond. Use Connect or Re-pair manually.")
            await self._close_diagnostics()
            if app_pairing:
                from .pairing import pair_linux
                from .linux_diagnostics import BlueZDiagnostics
                from .linux_discovery import LinuxConnectionDiscovery

                self.linux_diagnostics = BlueZDiagnostics(self.device, self._emit)
                try:
                    await self.linux_diagnostics.start()
                except Exception as error:
                    logger.warning("BlueZ diagnostics unavailable address=%s error=%s",
                                   self.address, safe_error(error))
                    self.linux_diagnostics = None
                discovery = LinuxConnectionDiscovery(self.device, self._emit)
                await discovery.start()
                fresh_pairing = await pair_linux(self.device, self.pairing_callback) if allow_pairing else False
                self._emit("progress", message=(
                    "PIN pairing completed; connecting…" if fresh_pairing else
                    "Using saved pairing; connecting without another PIN…"
                ))
            self.client = self.client_factory(
                self.device,
                disconnected_callback=self._on_disconnected,
                services=[protocol.SERVICE_UUID],
                pair=allow_pairing and not app_pairing,
                timeout=90.0 if allow_pairing else 25.0,
            )
            logger.debug("Awaiting Bleak connect address=%s", self.address)
            if app_pairing:
                try:
                    # PIN entry has already completed (or a bond was found).
                    # Do not let BlueZ silently retry a saved bond for 90 s.
                    async with asyncio.timeout(25.0):
                        await self.client.connect()
                except TimeoutError:
                    raise BoardError(
                        "The board is advertising, but Linux could not connect. "
                        "The saved pairing has been kept; see the debug log for details."
                    ) from None
            else:
                await self.client.connect()
            self.key_interval_ms = protocol.DEFAULT_KEY_INTERVAL_MS
            self.state.connected = True
            logger.info(
                "BLE link connected address=%s backend=%s",
                self.address,
                type(self.client).__name__,
            )
            logger.debug("Starting encrypted notifications address=%s", self.address)
            await self.client.start_notify(protocol.TX_UUID, self._on_notification)
            logger.info("Notifications enabled address=%s", self.address)
            # Notification subscription alone does not establish authentication:
            # require the board's own authenticated flag in the ping response.
            self.state.authenticated = False
            self.state.last_error = ""
            self._emit_state()
            await self.ping()
            if not self.state.authenticated:
                raise BoardError("board did not confirm authenticated pairing")
            if hasattr(self.client, "read_gatt_char"):
                try:
                    await self.read_info()
                except Exception as error:
                    # The optional characteristic is absent on stable 0.1.x.
                    # A capability lookup must not break an authenticated keyboard.
                    logger.info("Optional board information unavailable address=%s error=%s",
                                self.address, safe_error(error))
            if self.linux_diagnostics is not None:
                try:
                    await self.linux_diagnostics.snapshot("authenticated ping complete")
                except Exception as error:
                    logger.debug("BlueZ snapshot unavailable address=%s error=%s",
                                 self.address, safe_error(error))
        except asyncio.CancelledError:
            logger.info("Connect canceled address=%s", self.address)
            client = self.client
            if client is not None and client.is_connected:
                await client.disconnect()
            self.client = None
            self.state = BoardState(last_error="Connection canceled")
            self._emit_state()
            raise
        except Exception as error:
            message = safe_error(error)
            logger.exception("Connect failed address=%s error=%s", self.address, message)
            self.state = BoardState(last_error=message)
            self._emit_state()
            if self.client is not None and self.client.is_connected:
                await self.client.disconnect()
            self.client = None
            raise
        finally:
            self.connecting = False
            if discovery is not None:
                await discovery.close()
            if not self.state.connected:
                await self._close_diagnostics()

    async def _close_diagnostics(self) -> None:
        diagnostic, self.linux_diagnostics = self.linux_diagnostics, None
        if diagnostic is not None:
            await diagnostic.close()

    async def forget_bond(self) -> None:
        """Remove this board's OS-side bond without touching other devices."""
        if self.connecting:
            raise BoardError("wait for the current connection attempt to stop")
        await self._close_diagnostics()
        if self.client_factory is None:
            try:
                from bleak import BleakClient
            except ImportError as error:
                raise BoardError(
                    "Bleak is not installed; run pip install -r requirements.txt"
                ) from error
            self.client_factory = BleakClient

        if self.client is not None and self.client.is_connected:
            await self.client.disconnect()
        logger.info("Removing OS bond address=%s", self.address)
        client = self.client_factory(
            self.device,
            disconnected_callback=lambda _client=None: None,
            timeout=30.0,
        )
        await client.unpair()
        self.client = None
        self.state = BoardState()
        self._emit_state()
        logger.info("OS bond removed address=%s", self.address)

    async def disconnect(self) -> None:
        logger.info("Disconnect requested address=%s", self.address)
        client = self.client
        self.client = None
        if client is not None and client.is_connected:
            await client.disconnect()
        self._mark_disconnected("Disconnected")
        await self._close_diagnostics()

    def _on_disconnected(self, _client: Any) -> None:
        if self.connecting and not self.state.connected:
            # BlueZ may briefly establish and abort an LE link while Bleak's
            # connect() is still retrying. Bleak still owns that attempt.
            logger.debug(
                "Transient disconnect during connect address=%s; Bleak still owns retry",
                self.address,
            )
            return
        logger.warning("Unexpected BLE disconnect callback address=%s", self.address)
        self.client = None
        self._mark_disconnected("Connection lost; board marked disarmed")

    def _mark_disconnected(self, message: str) -> None:
        logger.info(
            "Marking disconnected address=%s reason=%s pending=%d",
            self.address,
            message,
            len(self.pending),
        )
        self.state = BoardState()
        for future in tuple(self.pending.values()):
            if not future.done():
                future.set_exception(BoardError("board disconnected"))
        self.pending.clear()
        self._emit_state()
        self._emit("disconnected", message=message)

    def _on_notification(self, _sender: Any, data: bytearray) -> None:
        try:
            status = protocol.parse_status(data)
        except protocol.ProtocolError as error:
            logger.warning(
                "Invalid notification address=%s length=%d error=%s",
                self.address,
                len(data),
                error,
            )
            self._emit("error", message=str(error))
            return

        logger.debug(
            "Notification address=%s status=%#04x sequence=%d "
            "authenticated=%s armed=%s typing=%s",
            self.address,
            status.status,
            status.sequence,
            status.authenticated,
            status.armed,
            status.typing,
        )

        self.state.authenticated = status.authenticated
        self.state.armed = status.armed
        self.state.typing = status.typing
        self._emit_state()

        pending = self.pending.pop(status.sequence, None)
        if pending is not None and not pending.done():
            logger.debug(
                "Notification matched request address=%s sequence=%d",
                self.address,
                status.sequence,
            )
            pending.set_result(status)
            return

        if pending is None:
            logger.debug(
                "Unsolicited notification address=%s sequence=%d status=%#04x",
                self.address,
                status.sequence,
                status.status,
            )

        event_names = {
            protocol.STATUS_TYPING_COMPLETE: "typing_complete",
            protocol.STATUS_TYPING_CANCELED: "typing_canceled",
            protocol.STATUS_STATE_CHANGED: "state_changed",
            protocol.STATUS_KEY_COMPLETE: "key_complete",
            protocol.STATUS_KEY_CANCELED: "key_canceled",
        }
        event = event_names.get(status.status)
        if event is not None:
            self._emit(event, message=event.replace("_", " ").capitalize())

    async def _request(self, frame: bytearray, sequence: int) -> protocol.StatusFrame:
        if self.client is None or not self.client.is_connected:
            raise BoardError("board is not connected")
        opcode = frame[1] if len(frame) > 1 else -1
        logger.debug(
            "GATT request address=%s opcode=%#04x sequence=%d length=%d",
            self.address,
            opcode,
            sequence,
            len(frame),
        )
        loop = asyncio.get_running_loop()
        response: asyncio.Future[protocol.StatusFrame] = loop.create_future()
        self.pending[sequence] = response
        write_task = asyncio.create_task(
            self.client.write_gatt_char(protocol.RX_UUID, frame, response=True)
        )
        try:
            # Bound the write too: BlueZ may leave WriteValue pending after the
            # link drops. Surface a disconnect immediately, even during a write.
            async with asyncio.timeout(10.0):
                await asyncio.wait((write_task, response), return_when=asyncio.FIRST_COMPLETED)
                if response.done():
                    response.result()
                await write_task
                status = await response
        except Exception as error:
            self.pending.pop(sequence, None)
            logger.exception(
                "GATT request failed address=%s opcode=%#04x sequence=%d error=%s",
                self.address,
                opcode,
                sequence,
                safe_error(error),
            )
            raise
        finally:
            self.pending.pop(sequence, None)
            if not write_task.done():
                write_task.cancel()
            await asyncio.gather(write_task, return_exceptions=True)
            if not response.done():
                response.cancel()
            elif not response.cancelled():
                response.exception()  # Consume a disconnect error if writing failed first.
            protocol.wipe(frame)
        if not status.ok:
            logger.warning(
                "Board rejected request address=%s opcode=%#04x sequence=%d "
                "status=%#04x message=%s",
                self.address,
                opcode,
                sequence,
                status.status,
                status.message,
            )
            raise BoardRejectedError(status.message, status.status)
        logger.debug(
            "GATT request acknowledged address=%s opcode=%#04x sequence=%d",
            self.address,
            opcode,
            sequence,
        )
        return status

    async def ping(self) -> float:
        sequence = self.sequences.take()
        frame = protocol.command_frame(protocol.OPCODE_PING, sequence)
        started = asyncio.get_running_loop().time()
        await self._request(frame, sequence)
        elapsed_ms = (asyncio.get_running_loop().time() - started) * 1000
        logger.info("Ping address=%s elapsed_ms=%.1f", self.address, elapsed_ms)
        self._emit("ping", milliseconds=round(elapsed_ms))
        return elapsed_ms

    async def read_info(self) -> protocol.BoardInfo:
        if self.client is None or not self.client.is_connected or not self.state.authenticated:
            raise BoardError("connect and authenticate before reading storage status")
        async with asyncio.timeout(10.0):
            raw = await self.client.read_gatt_char(protocol.INFO_UUID)
        info = protocol.parse_board_info(raw)
        self._emit("board_info", **asdict(info))
        return info

    async def storage_mode(self, allow_writes: bool) -> None:
        async with self.request_lock:
            if type(allow_writes) is not bool:
                raise BoardError("storage write permission must be a boolean")
            if self.state.armed or self.state.typing:
                raise BoardError("disarm the board before changing storage access")
            info = await self.read_info()
            if not info.supported:
                raise BoardError(protocol.STATUS_MESSAGES[11])
            if not info.present or info.error:
                raise BoardError(protocol.STATUS_MESSAGES[12])
            # Read-only to read/write is the one change allowed on a live export: a
            # read-only export holds no unwritten host data. Anything else needs a
            # host eject first (read/write could discard dirty cached writes).
            if info.exported and not (allow_writes and not info.writable):
                raise BoardError(protocol.STATUS_MESSAGES[13])
            in_place = info.exported
            sequence = self.sequences.take()
            self._emit("operation", message="Remounting USB drive; verifying access mode…")
            await self._request(protocol.storage_mode_frame(sequence, allow_writes), sequence)
            # The host may still issue a late eject after the command ACK.
            # Require a stable exported state; an ACK alone is not a mount.
            for _ in range(2):
                await asyncio.sleep(0.25)
                result = await self.read_info()
                if not result.present or result.error:
                    raise BoardError("SD became unavailable while remounting; check the UART log")
                if not result.exported:
                    raise BoardError(
                        "The computer ejected the drive again. Wait for eject to finish, "
                        "refresh Storage status, then retry mounting."
                    )
                if result.writable != allow_writes:
                    raise BoardError("The board did not confirm the requested storage access mode")
            if in_place:
                message = ("USB drive switched to read/write. The board briefly withdraws it, so your "
                           "computer re-detects the drive in a few seconds")
            else:
                message = "USB drive remounted read/write" if allow_writes else "USB drive remounted read-only"
            self._emit("operation", message=message)

    async def update_firmware(self, image, progress, cancelled=None) -> None:
        from .firmware_update import FirmwareRelease, upload_image
        async with self.request_lock:
            if not self.state.connected or not self.state.authenticated:
                raise BoardError("Connect and authenticate before updating firmware")
            if self.state.armed or self.state.typing:
                raise BoardError("Disarm before updating firmware")
            info = await self.read_info()
            if isinstance(image, FirmwareRelease):
                progress("Selecting and verifying firmware for the connected board…", 0)
                image = image.select(info.board)
            if info.board != image.board:
                raise BoardError("Firmware target does not match the selected board")
            await upload_image(self.client, image, progress, cancelled)

    async def send_text(self, text: str, key_interval_ms: int = protocol.DEFAULT_KEY_INTERVAL_MS) -> None:
        async with self.request_lock:
            frames = protocol.text_frames(text, self.sequences)
            logger.info(
                "Text send begin address=%s bytes=%d chunks=%d content=omitted",
                self.address,
                len(text.encode("ascii")),
                len(frames),
            )
            try:
                if key_interval_ms != self.key_interval_ms:
                    sequence = self.sequences.take()
                    try:
                        await self._request(protocol.key_interval_frame(sequence, key_interval_ms), sequence)
                    except BoardRejectedError as error:
                        if error.status_code == 2:
                            raise BoardError(
                                "Update the board to firmware 0.1.0 or newer to change the character delay"
                            ) from None
                        raise
                    self.key_interval_ms = key_interval_ms
                for frame in frames:
                    sequence = frame[2] | (frame[3] << 8)
                    await self._request(frame, sequence)
                self._emit("text_accepted", message="Text accepted; typing started")
                logger.info("Text accepted address=%s content=omitted", self.address)
            finally:
                for frame in frames:
                    protocol.wipe(frame)

    async def stop(self) -> None:
        async with self.request_lock:
            logger.info("Stop requested address=%s", self.address)
            sequence = self.sequences.take()
            await self._request(
                protocol.command_frame(protocol.OPCODE_STOP, sequence), sequence
            )
            self._emit("stopped", message="Stop acknowledged; board disarmed")

    async def key_action(self, key_code: int, modifiers: int = 0) -> None:
        async with self.request_lock:
            logger.info(
                "Key requested address=%s key_code=%#04x modifiers=%#04x",
                self.address,
                key_code,
                modifiers,
            )
            sequence = self.sequences.take()
            await self._request(
                protocol.key_frame(sequence, key_code, modifiers), sequence
            )
            self._emit("key_accepted", message="Key action accepted")

    async def identify(self, label: str = "") -> None:
        async with self.request_lock:
            logger.info("Identify requested address=%s", self.address)
            sequence = self.sequences.take()
            frame = protocol.identify_frame(sequence, label)
            has_label = len(frame) > 4
            try:
                await self._request(frame, sequence)
            except BoardRejectedError as error:
                if not has_label or error.status_code != 3:
                    raise
                # rc9 and earlier only accept the four-byte Identify command.
                sequence = self.sequences.take()
                await self._request(
                    protocol.command_frame(protocol.OPCODE_IDENTIFY, sequence), sequence
                )
                self._emit("identified", message=(
                    "Board is displaying its fixed ID; update firmware to show the renamed label"
                ))
            else:
                self._emit("identified", message=(
                    "Board is displaying its current name and ID" if has_label else
                    "Board is displaying its device ID"
                ))
