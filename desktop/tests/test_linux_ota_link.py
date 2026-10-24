import os
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch


@unittest.skipUnless(sys.platform == "linux", "BlueZ only")
class LinuxOtaLinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_acquires_selected_board_mtu_and_closes_socket_before_writes(self):
        from dbus_fast import Variant, MessageType
        from wits_keyboard.linux_ota_link import negotiated_write_size
        data_uuid = "f42aa902-5ac7-4b64-983a-2c4433216101"
        selected = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_01"
        other = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_02"
        objects = {}
        for path, address in ((selected, "AA:BB:CC:DD:EE:01"), (other, "AA:BB:CC:DD:EE:02")):
            objects[path] = {"org.bluez.Device1": {
                "Address": Variant("s", address), "Connected": Variant("b", True)}}
            objects[path + "/service/char"] = {"org.bluez.GattCharacteristic1": {
                "UUID": Variant("s", data_uuid), "WriteAcquired": Variant("b", False)}}
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, write_fd)
        calls = []
        class Bus:
            disconnected = False
            async def connect(self): pass
            async def call(self, message):
                calls.append(message)
                if message.member == "GetManagedObjects": body, fds = [objects], []
                elif message.member == "AcquireWrite": body, fds = [0, 517], [read_fd]
                else:
                    with self_test.assertRaises(OSError): os.fstat(read_fd)
                    body, fds = [Variant("b", False)], []
                return SimpleNamespace(message_type=MessageType.METHOD_RETURN, body=body, unix_fds=fds)
            def disconnect(self): self.disconnected = True
        self_test = self
        bus = Bus()
        with patch("dbus_fast.aio.MessageBus", return_value=bus):
            self.assertEqual(await negotiated_write_size("AA:BB:CC:DD:EE:01", data_uuid), 512)
        self.assertEqual([m.path for m in calls if m.member == "AcquireWrite"], [selected + "/service/char"])
        self.assertTrue(bus.disconnected)

    async def test_unavailable_device_falls_back_without_acquiring_any_write_lock(self):
        from dbus_fast import MessageType
        from wits_keyboard.linux_ota_link import negotiated_write_size
        calls = []
        class Bus:
            disconnected = False
            async def connect(self): pass
            async def call(self, message):
                calls.append(message)
                return SimpleNamespace(message_type=MessageType.METHOD_RETURN, body=[{}], unix_fds=[])
            def disconnect(self): self.disconnected = True
        bus = Bus()
        with patch("dbus_fast.aio.MessageBus", return_value=bus):
            self.assertIsNone(await negotiated_write_size("AA:BB:CC:DD:EE:01", "uuid"))
        self.assertEqual([m.member for m in calls], ["GetManagedObjects"])
        self.assertTrue(bus.disconnected)
