import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, create_autospec
from wits_keyboard.firmware_update import load_image, upload_image


class FirmwareFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        image = bytearray(40000)
        image[0] = 0xe9
        image[32:36] = bytes.fromhex("3254cdab")
        self.data = bytes(image)
        (self.root / "test.app.bin").write_bytes(self.data)
        self.manifest = dict(schema=1, board="waveshare7", chip="esp32s3", firmware="0.2.0-dev4",
                             filename="test.app.bin", size=len(self.data), sha256=hashlib.sha256(self.data).hexdigest())
        self.path = self.root / "test.ota.json"
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.manifest))


class FirmwareTests(FirmwareFixture, unittest.TestCase):
    def test_validates_local_image_and_hides_payload_repr(self):
        image = load_image(self.path)
        self.assertEqual(image.data, self.data)
        self.assertNotIn("data=", repr(image))

    def test_rejects_corrupt_image(self):
        (self.root / "test.app.bin").write_bytes(self.data[:-1] + b"x")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            load_image(self.path)

    def test_rejects_paths_and_factory_images(self):
        for name in ("../test.app.bin", "C:\\test.app.bin", "test.factory.bin", "/tmp/test.app.bin"):
            self.manifest["filename"] = name
            self.save()
            with self.assertRaises(ValueError):
                load_image(self.path)

    def test_rejects_size_and_wrong_image_header(self):
        self.manifest["size"] += 1
        self.save()
        with self.assertRaisesRegex(ValueError, "size"):
            load_image(self.path)
        self.manifest["size"] -= 1
        damaged = b"\0" + self.data[1:]
        (self.root / "test.app.bin").write_bytes(damaged)
        self.manifest["sha256"] = hashlib.sha256(damaged).hexdigest()
        self.save()
        with self.assertRaisesRegex(ValueError, "app-only"):
            load_image(self.path)


class ReleaseManifestTests(FirmwareFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        (self.root / "waveshare7").mkdir()
        other = bytearray(self.data)
        other[90] = 42
        self.other = bytes(other)
        (self.root / "waveshare7/wave.app.bin").write_bytes(self.other)
        self.manifest = dict(schema=2, firmware="0.2.0-dev9", images={
            "tqtpro": dict(chip="esp32s3", filename="test.app.bin", size=len(self.data),
                           sha256=hashlib.sha256(self.data).hexdigest()),
            "waveshare7": dict(chip="esp32s3", filename="waveshare7/wave.app.bin", size=len(self.other),
                               sha256=hashlib.sha256(self.other).hexdigest())})
        self.save()

    def test_selects_only_connected_model_and_requires_a_model(self):
        self.assertEqual(load_image(self.path, "tqtpro").data, self.data)
        self.assertEqual(load_image(self.path, "waveshare7").data, self.other)
        with self.assertRaisesRegex(ValueError, "board model"):
            load_image(self.path)
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            load_image(self.path, "unknown")

    def test_missing_target_cannot_fall_back_to_another_model(self):
        del self.manifest["images"]["tqtpro"]
        self.save()
        with self.assertRaisesRegex(ValueError, "no firmware"):
            load_image(self.path, "tqtpro")

    def test_unselected_binary_is_not_read_but_selected_corruption_is_rejected(self):
        (self.root / "waveshare7/wave.app.bin").unlink()
        self.assertEqual(load_image(self.path, "tqtpro").data, self.data)
        with self.assertRaises(FileNotFoundError):
            load_image(self.path, "waveshare7")
        (self.root / "test.app.bin").write_bytes(self.data[:-1] + b"x")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            load_image(self.path, "tqtpro")

    def test_rejects_escaping_paths_and_factory_images(self):
        for name in ("../test.app.bin", "/test.app.bin", "a/../test.app.bin", "a//test.app.bin",
                     "a/./test.app.bin", "C:/test.app.bin", "a\\test.app.bin", "test.factory.bin"):
            with self.subTest(name=name):
                self.manifest["images"]["tqtpro"]["filename"] = name
                self.save()
                with self.assertRaises(ValueError):
                    load_image(self.path, "tqtpro")

    def test_rejects_unknown_targets_and_invalid_descriptors(self):
        from copy import deepcopy
        original = deepcopy(self.manifest)
        changes = (("chip", "esp32c3"), ("size", True), ("sha256", "g" * 64), ("size", 50000000))
        for field, value in changes:
            with self.subTest(field=field, value=value):
                self.manifest = deepcopy(original)
                self.manifest["images"]["tqtpro"][field] = value
                self.save()
                with self.assertRaises(ValueError):
                    load_image(self.path, "tqtpro")
        self.manifest = deepcopy(original)
        self.manifest["images"]["unknown"] = self.manifest["images"].pop("tqtpro")
        self.save()
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            load_image(self.path, "waveshare7")

class FakeBle:
    def __init__(self):
        from types import SimpleNamespace
        from wits_keyboard.firmware_update import OTA_CONTROL_UUID, OTA_DATA_UUID, OTA_STATUS_UUID
        self.is_connected = True
        self.characteristics = {uuid: SimpleNamespace(uuid=uuid, max_write_without_response_size=64)
                                for uuid in (OTA_CONTROL_UUID, OTA_DATA_UUID, OTA_STATUS_UUID)}
        self.services = SimpleNamespace(get_characteristic=lambda uuid: self.characteristics.get(uuid))
        self.callback = None
        self.writes = []
        self.offset = self.count = 0
        self.tag = 0
        self.expected = 0
        self.received = bytearray()
        self.error = 0
        self.reject_finish = False
        self.drop_data_ack = False
        self.stopped = False

    def notify(self, status, detail=0):
        value = bytes([1, status, detail]) + self.tag.to_bytes(4, "little") + self.offset.to_bytes(4, "little")
        self.callback(None, bytearray(value))

    async def start_notify(self, _characteristic, callback):
        self.callback = callback

    async def stop_notify(self, _characteristic):
        self.stopped = True

    async def write_gatt_char(self, characteristic, frame, response):
        from wits_keyboard.firmware_update import OTA_CONTROL_UUID
        self.writes.append((characteristic.uuid, bytes(frame), response))
        if characteristic.uuid == OTA_CONTROL_UUID:
            command = frame[1]
            if command == 1:
                self.tag = int.from_bytes(frame[2:6], "little")
                self.expected = int.from_bytes(frame[6:10], "little")
                self.notify(3 if self.error else 0, self.error)
            elif command == 2:
                self.notify(3 if self.reject_finish else 2, 4 if self.reject_finish else 0)
            return
        assert not response
        assert int.from_bytes(frame[:4], "little") == self.tag
        assert int.from_bytes(frame[4:8], "little") == self.offset
        self.received.extend(frame[8:])
        self.offset += len(frame) - 8
        self.count += 1
        if self.drop_data_ack:
            self.is_connected = False
        elif self.count % 4 == 0 or self.offset == self.expected:
            self.notify(1)


class BluetoothUploadTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from wits_keyboard.firmware_update import FirmwareImage
        self.data = bytes(range(256)) * 3
        self.image = FirmwareImage("waveshare7", "test", "test.app.bin", hashlib.sha256(self.data).hexdigest(), self.data)
        self.client = FakeBle()
        self.progress = []

    async def test_windowed_upload_preserves_bytes_and_requires_final_verification(self):
        await upload_image(self.client, self.image, lambda *args: self.progress.append(args))
        self.assertEqual(bytes(self.client.received), self.data)
        self.assertTrue(all(len(frame) <= 64 for uuid, frame, response in self.client.writes if not response))
        self.assertEqual(self.progress[-1][1], 100)
        self.assertTrue(self.client.stopped)
        self.assertEqual(self.client.writes[-1][1][1], 2)

    async def test_reject_hash_error_without_success_and_send_abort(self):
        self.client.reject_finish = True
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            await upload_image(self.client, self.image, lambda *args: self.progress.append(args))
        self.assertFalse(any(value == 100 for _, value in self.progress))
        self.assertEqual(self.client.writes[-1][1][1], 3)

    async def test_busy_or_storage_error_sends_no_image_data(self):
        for error, message in [(1, "Disarm"), (2, "eject")]:
            client = FakeBle()
            client.error = error
            with self.assertRaisesRegex(ValueError, message):
                await upload_image(client, self.image, Mock())
            self.assertEqual(client.received, b"")

    async def test_legacy_firmware_is_rejected_before_any_write(self):
        self.client.characteristics.clear()
        with self.assertRaisesRegex(ValueError, "bootstrap"):
            await upload_image(self.client, self.image, Mock())
        self.assertFalse(self.client.writes)

    async def test_disconnect_fails_and_never_reports_verified(self):
        self.client.drop_data_ack = True
        with self.assertRaisesRegex(ValueError, "disconnected"):
            await upload_image(self.client, self.image, lambda *args: self.progress.append(args))
        self.assertFalse(any(value == 100 for _, value in self.progress))

    async def test_cancel_aborts_before_transmitting_image(self):
        import threading
        event = threading.Event()
        def cancel_on_ready(*args):
            event.set()
        with self.assertRaises(asyncio.CancelledError):
            await upload_image(self.client, self.image, cancel_on_ready, event)
        self.assertEqual(self.client.received, b"")
        self.assertTrue(self.client.stopped)

    async def test_tqtpro_uses_its_own_board_code_and_small_negotiated_writes(self):
        from dataclasses import replace
        from wits_keyboard.firmware_update import OTA_DATA_UUID
        self.client.characteristics[OTA_DATA_UUID].max_write_without_response_size = 20
        await upload_image(self.client, replace(self.image, board="tqtpro"), Mock())
        self.assertEqual(self.client.writes[0][1][10], 2)
        self.assertEqual(bytes(self.client.received), self.data)
        self.assertTrue(all(len(frame) <= 20 for _, frame, response in self.client.writes if not response))

    async def test_cancellation_during_transfer_sends_abort_without_commit(self):
        import threading
        event = threading.Event()
        def cancel_after_first_window(_message, value):
            if value > 0:
                event.set()
        with self.assertRaises(asyncio.CancelledError):
            await upload_image(self.client, self.image, cancel_after_first_window, event)
        self.assertGreater(len(self.client.received), 0)
        self.assertLess(len(self.client.received), len(self.data))
        self.assertEqual(self.client.writes[-1][1][1], 3)

    async def test_unrelated_notifications_are_ignored_and_invalid_offset_rejected(self):
        original = self.client.notify
        def notify(code, detail=0):
            self.client.callback(None, bytearray(b"invalid"))
            self.client.tag ^= 1
            original(3, 4)  # Another session's error must not cancel this one.
            self.client.tag ^= 1
            if code == 1:
                self.client.offset += 1
            original(code, detail)
        self.client.notify = notify
        with self.assertRaisesRegex(ValueError, "unexpected firmware offset"):
            await upload_image(self.client, self.image, Mock())
        self.assertEqual(self.client.writes[-1][1][1], 3)


    async def test_packet_size_can_grow_after_initial_minimum_mtu(self):
        from wits_keyboard.firmware_update import OTA_DATA_UUID
        characteristic = self.client.characteristics[OTA_DATA_UUID]
        characteristic.max_write_without_response_size = 20
        original = self.client.notify
        def notify(status, detail=0):
            if status == 1:
                characteristic.max_write_without_response_size = 512
            original(status, detail)
        self.client.notify = notify
        await upload_image(self.client, self.image, Mock())
        frames = [frame for _, frame, response in self.client.writes if not response]
        self.assertTrue(all(len(frame) <= 20 for frame in frames[:4]))
        self.assertTrue(any(len(frame) > 20 for frame in frames[4:]))
        self.assertEqual(bytes(self.client.received), self.data)

    @unittest.skipUnless(__import__("sys").platform == "linux", "BlueZ only")
    async def test_live_bluez_mtu_overrides_stale_characteristic_limit(self):
        from unittest.mock import patch, AsyncMock
        from wits_keyboard.firmware_update import OTA_DATA_UUID
        self.client.address = "AA:BB:CC:DD:EE:01"
        self.client.characteristics[OTA_DATA_UUID].max_write_without_response_size = 20
        with patch("wits_keyboard.linux_ota_link.negotiated_write_size", new_callable=AsyncMock, return_value=512) as query:
            await upload_image(self.client, self.image, Mock())
            query.assert_awaited_once()
        self.assertTrue(any(len(frame) > 20 for _, frame, response in self.client.writes if not response))
        self.assertEqual(bytes(self.client.received), self.data)

    async def test_progress_reports_speed_and_estimated_time(self):
        await upload_image(self.client, self.image, lambda *args: self.progress.append(args))
        self.assertTrue(any("KiB/s" in message and "remaining" in message for message, _ in self.progress))


try:
    from PySide6.QtWidgets import QApplication
    from wits_keyboard.app import AsyncRunner
    from wits_keyboard.firmware_dialog import FirmwareDialog
    from wits_keyboard.firmware_update import FirmwareImage
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False


@unittest.skipUnless(QT_AVAILABLE, "Qt not installed")
class FirmwareDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_upload_uses_runner_contract_and_tracks_cancellation(self):
        runner = create_autospec(AsyncRunner, instance=True)
        dialog = FirmwareDialog(runner, Mock(), "A")
        dialog.image = FirmwareImage("waveshare7", "test", "test.app.bin", "a" * 64, b"x" * 256)
        dialog._upload()
        runner.submit.assert_called_once()
        runner.submit.call_args.args[0].close() # Network is deliberately not started in this UI check.
        self.assertTrue(dialog.busy)
        self.assertTrue(dialog.close_button.isEnabled())
        self.assertIn("on_success", runner.submit.call_args.kwargs)
        dialog._progress("Verified", 100)
        dialog._finished(True, "Verified")
        self.assertFalse(dialog.busy)
        self.assertEqual(dialog.bar.value(), 100)
        dialog.close()

    def test_no_image_never_starts_upload(self):
        runner = create_autospec(AsyncRunner, instance=True)
        dialog = FirmwareDialog(runner, Mock(), "A")
        dialog._upload()
        runner.submit.assert_not_called()
        dialog.close()
