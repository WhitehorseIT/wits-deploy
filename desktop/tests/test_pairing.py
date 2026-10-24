import asyncio
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

try:
    if sys.platform != "linux":
        raise ImportError
    from dbus_fast import DBusError, MessageType, Variant
    from wits_keyboard.pairing import AGENT_PATH, PasskeyAgent, pair_linux
    PAIRING_AVAILABLE = True
except ImportError:
    PAIRING_AVAILABLE = False


class FakeBus:
    def __init__(self, *, paired=False, wait_for_pair=False):
        self.connected = False
        self.paired = paired
        self.wait_for_pair = wait_for_pair
        self.calls = []
        self.exports = {}
        self.pair_entered = asyncio.Event()

    async def connect(self):
        self.connected = True

    async def call(self, message):
        self.calls.append(message)
        body = []
        if message.member == "Get":
            body = [Variant("b", self.paired)]
        elif message.member == "Pair":
            self.pair_entered.set()
            if self.wait_for_pair:
                await asyncio.Future()
            await self.exports[AGENT_PATH].request_passkey(message.path)
        return SimpleNamespace(message_type=MessageType.METHOD_RETURN, body=body)

    def export(self, path, agent):
        self.exports[path] = agent

    def unexport(self, path):
        self.exports.pop(path, None)

    def disconnect(self):
        self.connected = False


@unittest.skipUnless(PAIRING_AVAILABLE, "Linux pairing dependencies not installed")
class PairingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.device = SimpleNamespace(
            address="AA:BB:CC:DD:EE:01", name="WITS Keyboard-test",
            details={"path": "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_01"},
        )

    async def test_exported_agent_interface_retains_bluez_name_and_passkey_signature(self):
        agent = PasskeyAgent(self.device, AsyncMock(return_value=123456))
        exported = agent.introspect()
        self.assertEqual(agent.name, "org.bluez.Agent1")
        self.assertEqual(exported.name, "org.bluez.Agent1")
        passkey = next(item for item in exported.methods if item.name == "RequestPasskey")
        self.assertEqual([arg.signature for arg in passkey.in_args], ["o"])
        self.assertEqual([arg.signature for arg in passkey.out_args], ["u"])
        self.assertEqual(agent.device_name, self.device.name)

    async def test_pair_uses_registered_agent_on_same_bus_without_changing_default(self):
        bus = FakeBus()
        callback = AsyncMock(return_value=123456)
        with patch("wits_keyboard.pairing.MessageBus", return_value=bus):
            await pair_linux(self.device, callback)
        callback.assert_awaited_once_with(self.device.address, self.device.name)
        self.assertEqual([call.member for call in bus.calls],
                         ["Get", "RegisterAgent", "Pair", "UnregisterAgent"])
        self.assertEqual(bus.calls[1].body, [AGENT_PATH, "KeyboardOnly"])
        self.assertFalse(bus.connected)
        self.assertFalse(bus.exports)

    async def test_existing_bond_does_not_prompt_or_pair(self):
        bus = FakeBus(paired=True)
        callback = AsyncMock()
        with patch("wits_keyboard.pairing.MessageBus", return_value=bus):
            await pair_linux(self.device, callback)
        callback.assert_not_awaited()
        self.assertEqual([call.member for call in bus.calls], ["Get"])
        self.assertFalse(bus.connected)

    async def test_cancel_connection_cancels_bluez_pairing_and_unregisters(self):
        bus = FakeBus(wait_for_pair=True)
        with patch("wits_keyboard.pairing.MessageBus", return_value=bus):
            task = asyncio.create_task(pair_linux(self.device, AsyncMock()))
            await bus.pair_entered.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual([call.member for call in bus.calls][-2:],
                         ["CancelPairing", "UnregisterAgent"])
        self.assertFalse(bus.connected)

    async def test_agent_rejects_other_device_without_requesting_pin(self):
        callback = AsyncMock()
        agent = PasskeyAgent(self.device, callback)
        with self.assertRaises(DBusError):
            await agent.request_passkey("/org/bluez/hci0/dev_OTHER")
        callback.assert_not_awaited()

    async def test_canceled_pin_is_not_accepted(self):
        agent = PasskeyAgent(self.device, AsyncMock(return_value=None))
        with self.assertRaises(DBusError) as result:
            await agent.request_passkey(self.device.details["path"])
        self.assertEqual(result.exception.type, "org.bluez.Error.Canceled")

    async def test_bluez_cancel_closes_pending_prompt(self):
        entered = asyncio.Event()
        async def prompt(_address, _name):
            entered.set()
            await asyncio.Future()
        agent = PasskeyAgent(self.device, prompt)
        task = asyncio.create_task(agent.request_passkey(self.device.details["path"]))
        await entered.wait()
        agent.cancel()
        with self.assertRaises(DBusError):
            await task
        self.assertIsNone(agent.prompt_task)
