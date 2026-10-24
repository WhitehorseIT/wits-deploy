import asyncio
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

try:
    if sys.platform != "linux":
        raise ImportError
    from dbus_fast import MessageType, Variant
    from wits_keyboard.linux_discovery import LinuxConnectionDiscovery
    AVAILABLE = True
except ImportError:
    AVAILABLE = False


class FakeDiscoveryBus:
    def __init__(self, *, connected=False, advertise=True):
        self.connected = connected
        self.advertise = advertise
        self.calls = []
        self.handler = None
        self.closed = False

    async def connect(self):
        pass

    def add_message_handler(self, handler):
        self.handler = handler

    def remove_message_handler(self, handler):
        self.handler = None

    async def call(self, message):
        self.calls.append(message)
        body = []
        if message.member == "GetAll":
            body = [{"Connected": Variant("b", self.connected)}]
        if message.member == "StartDiscovery" and self.advertise:
            self.handler(SimpleNamespace(
                message_type=MessageType.SIGNAL,
                path="/org/bluez/hci0/dev_AA_BB_CC_DD_EE_01",
                interface="org.freedesktop.DBus.Properties", member="PropertiesChanged",
                body=["org.bluez.Device1", {"RSSI": Variant("n", -50)}, []],
            ))
        return SimpleNamespace(message_type=MessageType.METHOD_RETURN, body=body)

    def disconnect(self):
        self.closed = True


@unittest.skipUnless(AVAILABLE, "Linux discovery dependencies not installed")
class LinuxDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.device = SimpleNamespace(
            address="AA:BB:CC:DD:EE:01",
            details={"path": "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_01"},
        )
        self.probe = LinuxConnectionDiscovery(self.device, Mock())

    async def test_discovery_stays_active_until_connection_owner_closes_it(self):
        bus = FakeDiscoveryBus()
        with patch("wits_keyboard.linux_discovery.MessageBus", return_value=bus):
            await self.probe.start()
            self.assertTrue(self.probe.seen.is_set())
            self.assertTrue(self.probe.started)
            self.assertFalse(bus.closed)
            self.assertNotIn("StopDiscovery", [call.member for call in bus.calls])
            await self.probe.close()
        self.assertEqual(bus.calls[-1].member, "StopDiscovery")
        self.assertTrue(bus.closed)
        self.assertNotIn("Pair", [call.member for call in bus.calls])
        self.assertNotIn("RemoveDevice", [call.member for call in bus.calls])

    async def test_existing_live_link_does_not_require_an_advertisement(self):
        bus = FakeDiscoveryBus(connected=True, advertise=False)
        with patch("wits_keyboard.linux_discovery.MessageBus", return_value=bus):
            await self.probe.start()
            await self.probe.close()
        self.assertEqual([call.member for call in bus.calls], ["GetAll"])

    async def test_cached_bond_change_is_not_a_live_advertisement(self):
        self.probe._on_message(SimpleNamespace(
            message_type=MessageType.SIGNAL, path=self.probe.path,
            interface="org.freedesktop.DBus.Properties", member="PropertiesChanged",
            body=["org.bluez.Device1", {"Paired": Variant("b", True)}, []],
        ))
        self.assertFalse(self.probe.seen.is_set())

    async def test_other_device_advertisement_does_not_satisfy_presence_check(self):
        self.probe._on_message(SimpleNamespace(
            message_type=MessageType.SIGNAL, path="/org/bluez/hci0/dev_OTHER",
            interface="org.freedesktop.DBus.Properties", member="PropertiesChanged",
            body=["org.bluez.Device1", {"RSSI": Variant("n", -40)}, []],
        ))
        self.assertFalse(self.probe.seen.is_set())

    async def test_missing_advertisement_reports_presence_not_authentication_and_cleans_up(self):
        bus = FakeDiscoveryBus(advertise=False)
        async def timeout_wait(awaitable, timeout):
            awaitable.close()
            raise TimeoutError
        with patch("wits_keyboard.linux_discovery.MessageBus", return_value=bus), \
                patch("wits_keyboard.linux_discovery.asyncio.wait_for", side_effect=timeout_wait):
            with self.assertRaisesRegex(RuntimeError, "did not see it advertising"):
                await self.probe.start()
        self.assertTrue(bus.closed)
        self.assertEqual(bus.calls[-1].member, "StopDiscovery")
