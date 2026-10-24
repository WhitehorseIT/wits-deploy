import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from wits_keyboard.controller import KeyboardController, DiscoveredBoard
from wits_keyboard.bonding import PairingRequired


class AutoConnectTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events = []
        self.controller = KeyboardController(lambda *event: self.events.append(event))
        self.auto = self.controller.reconnector
        self.device = SimpleNamespace(address="A", name="Board A")
        for address in ("A", "B"):
            self.controller.known_devices[address] = DiscoveredBoard(address, address)
        self.auto.enabled.add("A")

    async def asyncTearDown(self):
        await self.auto.stop()

    async def test_only_enabled_known_rows_connect_and_never_request_pairing(self):
        self.controller.connect = AsyncMock()
        await self.auto.attempt("B", self.device)
        await self.auto.attempt("unknown", self.device)
        self.controller.connect.assert_not_awaited()
        await self.auto.attempt("A", self.device)
        self.controller.connect.assert_awaited_once_with("A", allow_pairing=False)
        self.assertEqual(self.events[-1][2]["status"], "connected")

    async def test_failure_backoff_prevents_immediate_retry_and_is_bounded(self):
        self.controller.connect = AsyncMock(side_effect=RuntimeError("link unavailable"))
        for count, delay in ((1,5),(2,10),(3,20),(4,40),(5,60),(5,60)):
            before = asyncio.get_running_loop().time()
            await self.auto.attempt("A", self.device)
            actual_count, deadline = self.auto.retries["A"]
            self.assertEqual(actual_count, count)
            self.assertGreaterEqual(deadline, before+delay)
            self.assertNotIn("A", self.auto.eligible())
            self.auto.retries["A"] = (count, 0)  # Advance only this board's test deadline.

    async def test_missing_or_bad_bond_pauses_until_manual_resume(self):
        self.controller.connect = AsyncMock(side_effect=PairingRequired("pair manually"))
        await self.auto.attempt("A", self.device)
        self.assertIn("A", self.auto.paused)
        self.assertNotIn("A", self.auto.eligible())
        self.auto.resume("A")
        self.assertIn("A", self.auto.eligible())

    async def test_connected_pending_and_radio_busy_boards_are_skipped(self):
        self.controller.sessions["A"] = SimpleNamespace(state=SimpleNamespace(connected=True))
        self.assertFalse(self.auto.eligible())
        self.controller.sessions.clear()
        self.controller.connect_tasks["A"] = Mock()
        self.assertFalse(self.auto.eligible())
        self.controller.connect_tasks.clear()
        self.controller.repair_tasks["A"] = Mock()
        self.assertFalse(self.auto.eligible())
        self.controller.repair_tasks.clear()
        async with self.controller.radio_lock:
            self.assertFalse(self.auto.eligible())
        self.assertEqual(self.auto.eligible(), {"A"})

    async def test_manual_disconnect_pauses_watcher(self):
        session = SimpleNamespace(disconnect=AsyncMock())
        self.controller.sessions["A"] = session
        await self.controller.disconnect("A")
        self.assertIn("A", self.auto.paused)
        session.disconnect.assert_awaited_once()

    async def test_discovery_filters_devices_and_releases_adapter_before_connecting(self):
        owner = self
        class Scanner:
            def __init__(self, **kwargs): self.callback=kwargs["detection_callback"]
            async def __aenter__(self):
                owner.assertTrue(owner.controller.radio_lock.locked())
                self.callback(SimpleNamespace(address="unknown"), None)
                self.callback(SimpleNamespace(address="B"), None)
                self.callback(owner.device, None)
            async def __aexit__(self, *_args): pass
        with patch("bleak.BleakScanner", Scanner):
            found = await self.auto.discover({"A"})
        self.assertEqual(found, {"A": self.device})
        self.assertFalse(self.controller.radio_lock.locked())

    async def test_stop_cancels_scanning_and_prevents_later_connections(self):
        entered = asyncio.Event()
        async def discovery(_candidates):
            entered.set()
            await asyncio.Future()
        self.auto.discover = discovery
        self.controller.connect = AsyncMock()
        self.auto.configure("A", True)
        await asyncio.wait_for(entered.wait(), 1)
        await self.auto.stop()
        self.assertTrue(self.auto.task.done())
        self.controller.connect.assert_not_awaited()

    async def test_disable_during_connect_cancels_attempt_without_killing_other_watchers(self):
        entered = asyncio.Event()
        async def connect(**kwargs):
            entered.set()
            await asyncio.Future()
        self.controller.devices["A"] = self.device
        self.controller.sessions["A"] = SimpleNamespace(state=SimpleNamespace(connected=False), connect=connect)
        attempt = asyncio.create_task(self.auto.attempt("A", self.device))
        await asyncio.wait_for(entered.wait(), 1)
        self.auto.configure("A", False)
        await asyncio.wait_for(attempt, 1)
        self.assertIsNone(self.auto.current)
        self.assertFalse(self.controller.connect_tasks)
        self.assertFalse(self.controller.radio_lock.locked())

    async def test_connections_to_multiple_boards_are_serialized(self):
        active, maximum = 0, 0
        async def connect(**kwargs):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0)
            active -= 1
        for address in ("A", "B"):
            self.controller.devices[address] = SimpleNamespace(address=address)
            self.controller.sessions[address] = SimpleNamespace(state=SimpleNamespace(connected=False), connect=connect)
        await asyncio.gather(self.controller.connect("A"), self.controller.connect("B"))
        self.assertEqual(maximum, 1)

    async def test_ota_blocks_background_radio_operations_until_finished(self):
        entered, finish = asyncio.Event(), asyncio.Event()
        async def update(*_args):
            entered.set()
            await finish.wait()
        self.controller.sessions["B"] = SimpleNamespace(state=SimpleNamespace(connected=True), update_firmware=update)
        upload = asyncio.create_task(self.controller.update_firmware("B", None, None))
        await asyncio.wait_for(entered.wait(), 1)
        self.assertFalse(self.auto.eligible())
        finish.set()
        await upload
        self.assertEqual(self.auto.eligible(), {"A"})
