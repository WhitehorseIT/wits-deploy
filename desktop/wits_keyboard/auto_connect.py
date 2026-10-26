"""Watch opted-in saved boards and reconnect with bounded backoff."""
import asyncio
import logging
from . import protocol
from .bonding import PairingRequired, windows_link_is_up
from .logging_config import safe_error

logger = logging.getLogger(__name__)


class AutoConnector:
    def __init__(self, controller):
        self.controller = controller
        self.enabled, self.paused = set(), set()
        self.retries, self.last_status = {}, {}
        self.canceled_attempts = set()
        self.wake = asyncio.Event()
        self.task = self.current = None
        self.closed = False

    def emit(self, address, status, message):
        if self.last_status.get(address) != (status, message):
            self.last_status[address] = (status, message)
            self.controller._emit(address, "auto_connect", status=status, message=message)

    def configure(self, address, enabled):
        if enabled:
            self.enabled.add(address)
            self.resume(address)
            if self.task is None or self.task.done():
                self.task = asyncio.create_task(self.run(), name="saved-board-watcher")
        else:
            self.enabled.discard(address)
            self.pause(address)
            self.emit(address, "disabled", "Auto-connect disabled")
        self.wake.set()

    def pause(self, address):
        self.paused.add(address)
        if address in self.enabled:
            self.emit(address, "paused", "Auto-connect paused; Connect or toggle Auto-connect to resume")
        if self.current == address:
            self.canceled_attempts.add(address)
            task = self.controller.connect_tasks.get(address)
            if task is not None and not task.done():
                task.cancel()
        self.wake.set()

    def resume(self, address):
        self.paused.discard(address)
        self.retries.pop(address, None)
        self.wake.set()

    def eligible(self):
        now = asyncio.get_running_loop().time()
        if self.closed or self.controller.radio_lock.locked():
            return set()
        return {a for a in self.enabled-self.paused if a in self.controller.known_devices
                and a not in self.controller.connect_tasks and a not in self.controller.repair_tasks
                and not (a in self.controller.sessions and self.controller.sessions[a].state.connected)
                and now >= self.retries.get(a, (0, 0))[1]}

    async def discover(self, candidates):
        from bleak import BleakScanner
        found, seen = {}, asyncio.Event()
        def advertisement(device, _data):
            if device.address in candidates:
                found[device.address] = device
                seen.set()
        # Connection setup, explicit scans and OTA share this adapter lock.
        async with self.controller.radio_lock, self.controller.scan_lock:
            async with BleakScanner(detection_callback=advertisement, service_uuids=[protocol.SERVICE_UUID]):
                try:
                    await asyncio.wait_for(seen.wait(), 3)
                except TimeoutError:
                    pass
        return found

    async def unseen_but_linked(self, candidates, found):
        """Windows can hold a live link to a board that is therefore not advertising; connect to those directly."""
        linked = []
        for address in sorted(set(candidates) - set(found)):
            device = self.controller.devices.get(address)
            if device is not None and await windows_link_is_up(address):
                logger.info("Windows already links %s without advertisements; connecting directly", address)
                linked.append((address, device))
        return linked

    async def attempt(self, address, device):
        if address not in self.eligible():
            return
        self.controller.devices[address] = device
        self.current = address
        self.emit(address, "connecting", "Auto-connecting to saved board…")
        try:
            async with asyncio.timeout(60):
                await self.controller.connect(address, allow_pairing=False)
        except asyncio.CancelledError:
            if self.closed or address not in self.canceled_attempts:
                raise
        except Exception as error:
            message = safe_error(error)
            if isinstance(error, PairingRequired) or any(t in message.casefold() for t in
                    ("authentication", "authenticated pairing", "not paired", "notpaired", "insufficient encryption", "insufficient authorization")):
                self.paused.add(address)
                self.emit(address, "pairing_required", "Auto-connect paused: pair/re-pair manually. " + message)
            else:
                count = min(self.retries.get(address, (0, 0))[0]+1, 5)
                delay = min(5*2**(count-1), 60)
                self.retries[address] = (count, asyncio.get_running_loop().time()+delay)
                self.emit(address, "waiting", f"Auto-connect failed; retrying in {delay}s. {message}")
        else:
            self.retries.pop(address, None)
            self.emit(address, "connected", "Automatically connected and authenticated")
        finally:
            self.canceled_attempts.discard(address)
            self.current = None

    async def run(self):
        failures = 0
        while not self.closed and self.enabled:
            self.wake.clear()
            delay, candidates = 2, self.eligible()
            if candidates:
                for address in candidates:
                    self.emit(address, "watching", "Watching for this saved board in HID mode…")
                try:
                    found = await self.discover(candidates)
                    failures = 0
                    for address, device in found.items():
                        await self.attempt(address, device)
                    for address, device in await self.unseen_but_linked(candidates, found):
                        await self.attempt(address, device)
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    failures = min(failures+1, 5)
                    delay = min(5*2**(failures-1), 60)
                    logger.info("Auto-connect discovery unavailable: %s", safe_error(error))
                    for address in candidates:
                        self.emit(address, "waiting", f"Bluetooth scan unavailable; retrying in {delay}s")
            try:
                await asyncio.wait_for(self.wake.wait(), delay)
            except TimeoutError:
                pass

    async def stop(self):
        self.closed = True
        self.wake.set()
        if self.task is not None and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
