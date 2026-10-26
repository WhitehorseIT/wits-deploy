import unittest
import asyncio
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock, Mock

from wits_keyboard import protocol
from wits_keyboard.controller import KeyboardController, DiscoveredBoard
from wits_keyboard.session import BoardError, BoardRejectedError, BoardSession, BoardState


class FakeClient:
    def __init__(self, device, disconnected_callback, **options):
        self.device = device
        self.disconnected_callback = disconnected_callback
        self.options = options
        self.is_connected = False
        self.notification = None
        self.writes = []
        self.flags = 0x01
        self.next_status = protocol.STATUS_OK
        self.unpaired = False

    async def connect(self):
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False

    async def start_notify(self, _uuid, callback):
        self.notification = callback

    async def unpair(self):
        self.unpaired = True

    async def write_gatt_char(self, _uuid, frame, response):
        self.writes.append(bytes(frame))
        sequence = frame[2] | (frame[3] << 8)
        status = self.next_status
        self.next_status = protocol.STATUS_OK
        if frame[1] == protocol.OPCODE_TYPE_TEXT and frame[4] & protocol.TEXT_FLAG_END:
            self.flags |= 0x04
        if frame[1] == protocol.OPCODE_STOP:
            self.flags &= ~0x06
        self.notification(
            None,
            bytearray(
                (
                    protocol.PROTOCOL_VERSION,
                    status,
                    sequence & 0xFF,
                    sequence >> 8,
                    self.flags,
                )
            ),
        )


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events = []
        device = SimpleNamespace(address="AA:BB:CC:DD:EE:01", name="WITS Keyboard-0001")
        self.session = BoardSession(
            device,
            lambda address, event, details: self.events.append((address, event, details)),
            client_factory=FakeClient,
        )

    async def test_auto_connect_never_initiates_pairing_without_saved_bond(self):
        from wits_keyboard.bonding import PairingRequired
        with patch("wits_keyboard.session.has_saved_bond", AsyncMock(return_value=False)):
            with self.assertRaises(PairingRequired):
                await self.session.connect(allow_pairing=False)
        self.assertIsNone(self.session.client)
        self.assertFalse(self.session.state.connected)

    async def test_auto_connect_uses_saved_bond_without_requesting_pairing(self):
        with patch("wits_keyboard.session.has_saved_bond", AsyncMock(return_value=True)):
            await self.session.connect(allow_pairing=False)
        self.assertFalse(self.session.client.options["pair"])
        self.assertTrue(self.session.state.authenticated)
        self.assertFalse(self.session.state.armed)
        await self.session.disconnect()

    async def test_firmware_update_requires_disarmed_authenticated_matching_board(self):
        image = SimpleNamespace(board="tqtpro")
        self.session.read_info = AsyncMock(return_value=SimpleNamespace(board="waveshare7"))
        with patch("wits_keyboard.firmware_update.upload_image", new_callable=AsyncMock) as upload:
            with self.assertRaisesRegex(BoardError, "authenticate"):
                await self.session.update_firmware(image, Mock())
            self.session.state = BoardState(connected=True, authenticated=True, armed=True)
            with self.assertRaisesRegex(BoardError, "Disarm"):
                await self.session.update_firmware(image, Mock())
            self.session.state.armed = False
            with self.assertRaisesRegex(BoardError, "target"):
                await self.session.update_firmware(image, Mock())
            upload.assert_not_awaited()

    async def test_firmware_update_holds_session_lock_for_the_upload(self):
        self.session.state = BoardState(connected=True, authenticated=True)
        self.session.read_info = AsyncMock(return_value=SimpleNamespace(board="tqtpro"))
        async def upload(*_args):
            self.assertTrue(self.session.request_lock.locked())
        with patch("wits_keyboard.firmware_update.upload_image", side_effect=upload) as uploader:
            await self.session.update_firmware(SimpleNamespace(board="tqtpro"), Mock())
            uploader.assert_awaited_once()
        self.assertFalse(self.session.request_lock.locked())

    async def test_unified_release_selects_from_connected_model_before_upload(self):
        from pathlib import Path
        from wits_keyboard.firmware_update import FirmwareRelease
        release = FirmwareRelease("test", Path("/unused"), ())
        image = SimpleNamespace(board="waveshare7")
        self.session.state = BoardState(connected=True, authenticated=True)
        self.session.read_info = AsyncMock(return_value=SimpleNamespace(board="waveshare7"))
        with patch.object(FirmwareRelease, "select", return_value=image) as selector:
            with patch("wits_keyboard.firmware_update.upload_image", new_callable=AsyncMock) as upload:
                await self.session.update_firmware(release, Mock())
                selector.assert_called_once_with("waveshare7")
                self.assertIs(upload.call_args.args[1], image)

    async def test_unified_release_missing_board_cannot_start_upload(self):
        from pathlib import Path
        from wits_keyboard.firmware_update import FirmwareRelease
        release = FirmwareRelease("test", Path("/unused"), ())
        self.session.state = BoardState(connected=True, authenticated=True)
        self.session.read_info = AsyncMock(return_value=SimpleNamespace(board="tqtpro"))
        with patch("wits_keyboard.firmware_update.upload_image", new_callable=AsyncMock) as upload:
            with self.assertRaisesRegex(ValueError, "no firmware"):
                await self.session.update_firmware(release, Mock())
            upload.assert_not_awaited()

    async def test_windows_reconnects_once_when_the_service_list_is_incomplete(self):
        calls = []

        class FlakyClient(FakeClient):
            async def start_notify(self, uuid, callback):
                calls.append("start_notify")
                if calls.count("start_notify") == 1:
                    raise RuntimeError("Characteristic 7cb2a248 was not found!")
                await super().start_notify(uuid, callback)

            async def connect(self):
                calls.append("connect")
                await super().connect()

            async def disconnect(self):
                calls.append("disconnect")
                await super().disconnect()

        self.session.client_factory = FlakyClient
        with patch("wits_keyboard.session.sys.platform", "win32"), \
                patch("wits_keyboard.session.asyncio.sleep", AsyncMock()), \
                patch("wits_keyboard.session.has_saved_bond", AsyncMock(return_value=True)):
            await self.session.connect(allow_pairing=False)
        self.assertEqual(calls, ["connect", "start_notify", "disconnect", "connect", "start_notify"])
        self.assertTrue(self.session.state.authenticated)
        await self.session.disconnect()

    async def test_windows_explains_a_service_list_that_stays_incomplete(self):
        class BrokenClient(FakeClient):
            async def start_notify(self, uuid, callback):
                raise RuntimeError("Characteristic 7cb2a248 was not found!")

        self.session.client_factory = BrokenClient
        with patch("wits_keyboard.session.sys.platform", "win32"), \
                patch("wits_keyboard.session.asyncio.sleep", AsyncMock()), \
                patch("wits_keyboard.session.has_saved_bond", AsyncMock(return_value=True)):
            with self.assertRaisesRegex(BoardError, "Remove, then pair"):
                await self.session.connect(allow_pairing=False)
        self.assertFalse(self.session.state.connected)

    async def test_other_systems_do_not_retry_a_missing_characteristic(self):
        class BrokenClient(FakeClient):
            async def start_notify(self, uuid, callback):
                raise RuntimeError("Characteristic 7cb2a248 was not found!")

        self.session.client_factory = BrokenClient
        with patch("wits_keyboard.session.sys.platform", "linux"), \
                patch("wits_keyboard.session.has_saved_bond", AsyncMock(return_value=True)):
            with self.assertRaisesRegex(RuntimeError, "not found"):
                await self.session.connect(allow_pairing=False)

    async def test_an_unexpected_disconnect_releases_the_os_connection(self):
        """Windows re-links a board behind the app's back until its client disconnects."""
        released = []

        class ReleasingClient(FakeClient):
            async def disconnect(self):
                released.append("disconnect")
                await super().disconnect()

        self.session.client_factory = ReleasingClient
        with patch("wits_keyboard.session.has_saved_bond", AsyncMock(return_value=True)):
            await self.session.connect(allow_pairing=False)
        self.session._on_disconnected(self.session.client)
        await asyncio.sleep(0.05)
        self.assertEqual(released, ["disconnect"])
        self.assertFalse(self.session.state.connected)
        self.assertIsNone(self.session.client)

    async def test_a_board_that_stops_answering_is_marked_lost_within_a_few_checks(self):
        class DeafClient(FakeClient):
            answer = True

            async def write_gatt_char(self, uuid, frame, response):
                if self.answer:
                    await super().write_gatt_char(uuid, frame, response)  # silence after this flips off

        self.session.client_factory = DeafClient
        with patch("wits_keyboard.session.has_saved_bond", AsyncMock(return_value=True)), \
                patch("wits_keyboard.session.HEARTBEAT_INTERVAL_S", 0.01), \
                patch("wits_keyboard.session.HEARTBEAT_TIMEOUT_S", 0.05):
            await self.session.connect(allow_pairing=False)
            self.assertTrue(self.session.state.connected)
            client = self.session.client
            client.answer = False
            for _ in range(100):
                await asyncio.sleep(0.02)
                if not self.session.state.connected:
                    break
        self.assertFalse(self.session.state.connected)
        self.assertIsNone(self.session.client)
        self.assertTrue(any(event[1] == "disconnected" for event in self.events))

    async def test_heartbeats_are_quiet_and_do_not_interrupt_a_busy_session(self):
        with patch("wits_keyboard.session.has_saved_bond", AsyncMock(return_value=True)), \
                patch("wits_keyboard.session.HEARTBEAT_INTERVAL_S", 0.01):
            await self.session.connect(allow_pairing=False)
            pings_before = sum(1 for event in self.events if event[1] == "ping")
            await asyncio.sleep(0.15)  # many heartbeats go by
            pings_after = sum(1 for event in self.events if event[1] == "ping")
            self.assertEqual(pings_before, pings_after)  # heartbeats never show up as "Ping acknowledged"
            self.assertTrue(self.session.state.connected)
            async with self.session.request_lock:  # a request in progress: no heartbeat is sent over it
                writes = len(self.session.client.writes)
                await asyncio.sleep(0.1)
                self.assertEqual(len(self.session.client.writes), writes)
            await self.session.disconnect()

    async def test_connect_requests_pairing_and_pings(self):
        await self.session.connect()
        self.assertTrue(self.session.state.connected)
        self.assertTrue(self.session.state.authenticated)
        self.assertTrue(self.session.client.options["pair"])
        self.assertEqual(self.session.client.options["timeout"], 90.0)
        self.assertEqual(self.session.client.writes[0][1], protocol.OPCODE_PING)
        self.assertTrue(any(event == "ping" for _, event, _ in self.events))

    async def test_legacy_keyboard_connects_when_optional_storage_characteristic_is_absent(self):
        class LegacyKeyboard(FakeClient):
            async def read_gatt_char(self, _uuid):
                raise RuntimeError("Characteristic not found")
        self.session.client_factory = LegacyKeyboard
        await self.session.connect()
        self.assertTrue(self.session.state.connected)
        self.assertTrue(self.session.state.authenticated)
        await self.session.ping()
        self.assertTrue(any(event == "ping" for _, event, _ in self.events))

    async def test_text_chunks_are_sent_once(self):
        await self.session.connect()
        self.session.client.flags = 0x03
        await self.session.send_text("A" * 121)
        text_writes = [
            frame for frame in self.session.client.writes
            if frame[1] == protocol.OPCODE_TYPE_TEXT
        ]
        self.assertEqual(len(text_writes), 2)
        self.assertEqual(text_writes[0][4], protocol.TEXT_FLAG_START)
        self.assertEqual(text_writes[1][4], protocol.TEXT_FLAG_END)

    async def test_character_interval_is_acknowledged_before_text(self):
        await self.session.connect()
        await self.session.send_text("ABC", 500)
        writes = self.session.client.writes[1:]
        self.assertEqual(writes[0][1], protocol.OPCODE_KEY_INTERVAL)
        self.assertEqual(writes[0][4:], b"\xf4\x01")
        self.assertEqual(writes[1][1], protocol.OPCODE_TYPE_TEXT)
        self.assertEqual(self.session.key_interval_ms, 500)

    async def test_legacy_firmware_rejection_does_not_send_text_at_wrong_speed(self):
        await self.session.connect()
        self.session.client.next_status = 2
        with self.assertRaisesRegex(BoardError, r"0\.1\.0"):
            await self.session.send_text("ABC", 500)
        self.assertFalse(any(frame[1] == protocol.OPCODE_TYPE_TEXT for frame in self.session.client.writes))
        self.assertEqual(self.session.key_interval_ms, 25)

    async def test_character_interval_can_return_to_default_in_same_session(self):
        await self.session.connect()
        await self.session.send_text("A", 500)
        await self.session.send_text("B", 25)
        intervals = [frame[4:] for frame in self.session.client.writes
                     if frame[1] == protocol.OPCODE_KEY_INTERVAL]
        self.assertEqual(intervals, [b"\xf4\x01", b"\x19\x00"])

    async def test_identify_sends_current_label(self):
        await self.session.connect()
        await self.session.identify("Device 1")
        self.assertEqual(self.session.client.writes[-1][4:], b"Device 1")

    async def test_identify_falls_back_only_on_legacy_length_rejection(self):
        await self.session.connect()
        self.session.client.next_status = 3
        await self.session.identify("Device 1")
        identify = [frame for frame in self.session.client.writes if frame[1] == 0x13]
        self.assertEqual(len(identify), 2)
        self.assertEqual(len(identify[-1]), 4)
        self.assertTrue(any("update firmware" in details.get("message", "")
                            for _, _, details in self.events))

    async def test_identify_busy_is_not_retried(self):
        await self.session.connect()
        self.session.client.next_status = 5
        with self.assertRaises(BoardRejectedError):
            await self.session.identify("Device 1")
        identify = [frame for frame in self.session.client.writes if frame[1] == 0x13]
        self.assertEqual(len(identify), 1)

    async def test_board_rejection_is_not_hidden(self):
        await self.session.connect()
        self.session.client.next_status = 4
        with self.assertRaisesRegex(BoardRejectedError, "not armed"):
            await self.session.key_action(protocol.KEY_ENTER)

    async def test_transient_disconnect_during_connect_keeps_client(self):
        self.session.connecting = True
        marker = object()
        self.session.client = marker

        self.session._on_disconnected(None)

        self.assertIs(self.session.client, marker)
        self.assertFalse(self.session.state.connected)

    async def test_disconnect_message_does_not_imply_prior_arming(self):
        self.session.state = BoardState(
            connected=True, authenticated=True, armed=False
        )

        self.session._on_disconnected(None)

        disconnects = [
            details["message"]
            for _, event, details in self.events
            if event == "disconnected"
        ]
        self.assertEqual(disconnects, ["Connection lost; board marked disarmed"])
        self.assertFalse(self.session.state.armed)

    async def test_forget_bond_uses_platform_client(self):
        await self.session.forget_bond()
        self.assertIsNone(self.session.client)
        self.assertTrue(any(event == "state" for _, event, _ in self.events))

    async def test_connection_requires_authenticated_ping_not_just_subscription(self):
        class UnauthenticatedClient(FakeClient):
            async def connect(self):
                await super().connect()
                self.flags = 0
        self.session.client_factory = UnauthenticatedClient
        with self.assertRaisesRegex(BoardError, "authenticated pairing"):
            await self.session.connect()
        self.assertFalse(self.session.state.authenticated)
        self.assertFalse(self.session.state.connected)

    async def test_disconnect_during_stalled_write_fails_promptly_and_cleans_pending(self):
        await self.session.connect()
        started = asyncio.Event()
        async def stalled_write(*args, **kwargs):
            started.set()
            await asyncio.Future()
        self.session.client.write_gatt_char = stalled_write
        task = asyncio.create_task(self.session.ping())
        await started.wait()
        self.session._on_disconnected(None)
        with self.assertRaisesRegex(BoardError, "board disconnected"):
            await asyncio.wait_for(task, timeout=0.5)
        self.assertFalse(self.session.pending)

    async def test_cancel_during_stalled_write_cleans_pending(self):
        await self.session.connect()
        started = asyncio.Event()
        async def stalled_write(*args, **kwargs):
            started.set()
            await asyncio.Future()
        self.session.client.write_gatt_char = stalled_write
        task = asyncio.create_task(self.session.ping())
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(self.session.pending)


class FakeSession:
    def __init__(self, failure=None):
        self.state = BoardState(connected=True, authenticated=True, armed=True)
        self.failure = failure
        self.calls = 0

    async def send_text(self, _text, key_interval_ms=25):
        self.calls += 1
        if self.failure is not None:
            raise self.failure


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_remembered_device_can_connect_without_manual_scan(self):
        controller = KeyboardController(lambda *_: None)
        controller.known_devices["saved"] = DiscoveredBoard("saved", "WITS Keyboard")
        device = SimpleNamespace(address="saved", name="WITS Keyboard")
        session = Mock(connect=AsyncMock())
        with patch.object(controller, "_resolve_device", AsyncMock(return_value=device)), \
                patch("wits_keyboard.controller.BoardSession", return_value=session):
            await controller.connect("saved")
        session.connect.assert_awaited_once()
        self.assertFalse(controller.connect_tasks)

    async def test_disconnect_cancels_saved_device_resolution(self):
        controller = KeyboardController(lambda *_: None)
        controller.known_devices["saved"] = DiscoveredBoard("saved", "WITS Keyboard")
        started = asyncio.Event()
        async def resolve(_address):
            started.set()
            await asyncio.Future()
        with patch.object(controller, "_resolve_device", side_effect=resolve):
            task = asyncio.create_task(controller.connect("saved"))
            await started.wait()
            await controller.disconnect("saved")
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertFalse(controller.connect_tasks)

    async def test_disconnect_cancels_repair_during_rediscovery(self):
        controller = KeyboardController(lambda *_: None)
        started = asyncio.Event()
        async def rediscovery(_address, _timeout):
            started.set()
            await asyncio.Future()
        with patch.object(controller, "_repair", side_effect=rediscovery):
            task = asyncio.create_task(controller.repair("test"))
            await started.wait()
            await controller.disconnect("test")
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertFalse(controller.repair_tasks)

    async def test_multi_send_reports_each_board_and_never_retries(self):
        events = []
        controller = KeyboardController(
            lambda address, event, details: events.append((address, event, details))
        )
        good = FakeSession()
        bad = FakeSession(RuntimeError("link lost"))
        controller.sessions = {"good": good, "bad": bad}

        await controller.send_text_many(("good", "bad"), "secret")

        self.assertEqual(good.calls, 1)
        self.assertEqual(bad.calls, 1)
        outcomes = {address: details for address, event, details in events if event == "operation"}
        self.assertTrue(outcomes["good"]["success"])
        self.assertFalse(outcomes["bad"]["success"])
        self.assertEqual(outcomes["bad"]["message"], "link lost")


if __name__ == "__main__":
    unittest.main()
