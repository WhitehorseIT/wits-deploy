import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from wits_keyboard import protocol
from wits_keyboard.session import BoardSession, BoardState, BoardError


def info(**changes):
    value = dict(schema=1, firmware="0.2.0-dev", board="waveshare7", supported=True,
                 present=True, exported=False, writable=False, ejected=True, error=False,
                 bytes=32 * 1024 * 1024 * 1024)
    value.update(changes)
    return json.dumps(value).encode()


class StorageProtocolTests(unittest.TestCase):
    def test_large_capacity_and_version_are_preserved(self):
        parsed = protocol.parse_board_info(info())
        self.assertEqual(parsed.bytes, 34359738368)
        self.assertEqual(parsed.firmware, "0.2.0-dev")

    def test_reject_malformed_states(self):
        invalid = [b"", b"{}", b"[]", b"\xff", info(schema=True), info(schema=2),
                   info(writable=1), info(bytes=True), info(bytes=-1),
                   info(writable=True, exported=False), info(firmware="bad\nlabel")]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(protocol.ProtocolError):
                protocol.parse_board_info(value)

    def test_storage_command_requires_explicit_boolean(self):
        self.assertEqual(protocol.storage_mode_frame(0x1234, True), bytes([2, 0x15, 0x34, 0x12, 1]))
        self.assertEqual(protocol.storage_mode_frame(1, False), bytes([2, 0x15, 1, 0, 0]))
        with self.assertRaises(protocol.ProtocolError):
            protocol.storage_mode_frame(1, 1)


class StorageSessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.events = []
        self.session = BoardSession(SimpleNamespace(address="A", name="Board A"),
                                    lambda *event: self.events.append(event))
        self.session.state = BoardState(connected=True, authenticated=True)
        self.session.client = SimpleNamespace(is_connected=True, read_gatt_char=AsyncMock(return_value=info()))
        self.session._request = AsyncMock()

    async def test_ejected_board_can_remount_writable_and_refresh(self):
        self.session.client.read_gatt_char.side_effect = [
            info(), info(exported=True, ejected=False, writable=True),
            info(exported=True, ejected=False, writable=True),
        ]
        await self.session.storage_mode(True)
        frame, sequence = self.session._request.call_args.args
        self.assertEqual(frame, protocol.storage_mode_frame(sequence, True))
        self.assertEqual(self.session.client.read_gatt_char.await_count, 3)

    async def test_late_host_eject_does_not_report_success(self):
        self.session.client.read_gatt_char.side_effect = [
            info(), info(exported=True, ejected=False, writable=True), info(),
        ]
        with self.assertRaisesRegex(BoardError, "ejected the drive again"):
            await self.session.storage_mode(True)
        self.assertFalse(any("remounted" in event[2].get("message", "") for event in self.events))

    async def test_revoked_access_during_remount_does_not_report_success(self):
        self.session.client.read_gatt_char.side_effect = [
            info(), info(exported=True, ejected=False, writable=False),
        ]
        with self.assertRaisesRegex(BoardError, "did not confirm"):
            await self.session.storage_mode(True)

    async def test_read_only_remount_verifies_protection(self):
        self.session.client.read_gatt_char.side_effect = [
            info(), info(exported=True, ejected=False), info(exported=True, ejected=False),
        ]
        await self.session.storage_mode(False)
        self.assertIn("read-only", self.events[-1][2]["message"])

    async def test_live_read_only_export_switches_to_writable_without_an_eject(self):
        self.session.client.read_gatt_char.side_effect = [
            info(exported=True, ejected=False, writable=False),   # before the command
            info(exported=True, ejected=False, writable=True),    # verification reads
            info(exported=True, ejected=False, writable=True),
        ]
        await self.session.storage_mode(True)
        frame, sequence = self.session._request.call_args.args
        self.assertEqual(frame, protocol.storage_mode_frame(sequence, True))
        self.assertIn("re-detects the drive", self.events[-1][2]["message"])

    async def test_every_other_change_on_a_live_export_still_requires_an_eject(self):
        cases = [
            (dict(exported=True, ejected=False, writable=False), False),  # read-only to read-only
            (dict(exported=True, ejected=False, writable=True), False),   # read/write to read-only
            (dict(exported=True, ejected=False, writable=True), True),    # read/write to read/write
        ]
        for state, allow in cases:
            with self.subTest(state=state, allow=allow):
                self.session.client.read_gatt_char.return_value = info(**state)
                with self.assertRaisesRegex(BoardError, "safely eject"):
                    await self.session.storage_mode(allow)
        self.session._request.assert_not_called()

    async def test_live_switch_is_not_reported_if_the_board_did_not_confirm_writes(self):
        self.session.client.read_gatt_char.side_effect = [
            info(exported=True, ejected=False, writable=False),
            info(exported=True, ejected=False, writable=False),
        ]
        with self.assertRaisesRegex(BoardError, "did not confirm"):
            await self.session.storage_mode(True)

    async def test_unsupported_missing_card_and_io_error_never_send_command(self):
        for changes in [dict(supported=False), dict(present=False), dict(error=True)]:
            self.session.client.read_gatt_char.return_value = info(**changes)
            with self.assertRaises(BoardError):
                await self.session.storage_mode(True)
        self.session._request.assert_not_called()

    async def test_armed_or_typing_blocks_storage_changes(self):
        for state in [BoardState(connected=True, authenticated=True, armed=True),
                      BoardState(connected=True, authenticated=True, typing=True)]:
            self.session.state = state
            with self.assertRaisesRegex(BoardError, "disarm"):
                await self.session.storage_mode(True)
        self.session._request.assert_not_called()

    async def test_no_authentication_cannot_read_storage(self):
        self.session.state.authenticated = False
        with self.assertRaisesRegex(BoardError, "authenticate"):
            await self.session.read_info()
        self.session.client.read_gatt_char.assert_not_called()

    async def test_read_timeout_is_bounded(self):
        async def stalled(_uuid):
            raise TimeoutError
        self.session.client.read_gatt_char.side_effect = stalled
        with self.assertRaises(TimeoutError):
            await self.session.read_info()

    async def test_legacy_missing_characteristic_does_not_send_storage_command(self):
        self.session.client.read_gatt_char.side_effect = RuntimeError("characteristic not found")
        with self.assertRaisesRegex(RuntimeError, "characteristic not found"):
            await self.session.storage_mode(True)
        self.session._request.assert_not_called()
