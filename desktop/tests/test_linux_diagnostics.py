import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

try:
    if sys.platform != "linux":
        raise ImportError
    from dbus_fast import MessageType, Variant
    from wits_keyboard.linux_diagnostics import BlueZDiagnostics, cached_linux_device
    AVAILABLE = True
except ImportError:
    AVAILABLE = False


@unittest.skipUnless(AVAILABLE, "Linux diagnostics dependencies not installed")
class DiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.device = SimpleNamespace(
            address="AA:BB:CC:DD:EE:01",
            details={"path": "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_01"},
        )
        self.callback = Mock()
        self.monitor = BlueZDiagnostics(self.device, self.callback)

    async def test_saved_board_resolves_from_bluez_cache_without_scanning(self):
        bus = Mock()
        bus.connect = AsyncMock()
        bus.call = AsyncMock(return_value=SimpleNamespace(
            message_type=MessageType.METHOD_RETURN,
            body=[{self.device.details["path"]: {"org.bluez.Device1": {
                "Address": Variant("s", self.device.address),
                "Name": Variant("s", "WITS Keyboard-test"),
                "Paired": Variant("b", True),
            }}}],
        ))
        with patch("wits_keyboard.linux_diagnostics.MessageBus", return_value=bus):
            resolved = await cached_linux_device(self.device.address)
        self.assertEqual(resolved.address, self.device.address)
        self.assertEqual(resolved.details["path"], self.device.details["path"])
        self.assertTrue(resolved.details["props"]["Paired"])
        bus.disconnect.assert_called_once()

    def signal(self, *, path=None, interface="org.bluez.Device1",
               member="Disconnected", body=None):
        return SimpleNamespace(
            message_type=MessageType.SIGNAL,
            path=path or self.monitor.path, interface=interface, member=member,
            body=body if body is not None else ["org.bluez.Reason.Authentication", "Failure"],
        )

    async def test_authentication_reason_provides_targeted_repair_message(self):
        self.monitor._on_message(self.signal())
        args, details = self.callback.call_args
        self.assertEqual(args, ("link_diagnostic",))
        self.assertEqual(details["reason"], "org.bluez.Reason.Authentication")
        self.assertIn("Re-pair", details["message"])

    async def test_other_devices_do_not_generate_diagnostic_events(self):
        self.monitor._on_message(self.signal(path="/org/bluez/hci0/dev_OTHER"))
        self.callback.assert_not_called()

    async def test_properties_logging_excludes_values_and_advertising_payload(self):
        with self.assertLogs("wits_keyboard.linux_diagnostics", level="INFO") as captured:
            self.monitor._on_message(self.signal(
                interface="org.freedesktop.DBus.Properties", member="PropertiesChanged",
                body=["org.bluez.Device1", {
                    "Connected": Variant("b", True),
                    "Value": Variant("ay", b"do-not-log-this"),
                }, []],
            ))
        self.assertIn("Connected", str(captured.output))
        self.assertNotIn("do-not-log-this", str(captured.output))

    async def test_start_failure_closes_private_bus(self):
        bus = Mock()
        bus.connect = AsyncMock()
        bus.call = AsyncMock(side_effect=OSError("test failure"))
        with patch("wits_keyboard.linux_diagnostics.MessageBus", return_value=bus):
            with self.assertRaises(OSError):
                await self.monitor.start()
        bus.disconnect.assert_called_once()
        self.assertIsNone(self.monitor.bus)
