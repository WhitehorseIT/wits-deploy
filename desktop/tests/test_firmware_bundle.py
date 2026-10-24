import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from wits_keyboard.firmware_bundle import stage_release, bundled_manifest
from wits_keyboard.firmware_update import BOARD_CODES


class BundleFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / "release.ota.json"
        images = {}
        for index, board in enumerate(BOARD_CODES):
            folder = self.root / board
            folder.mkdir()
            app = bytearray(400)
            app[0] = 0xe9
            app[32:36] = bytes.fromhex("3254cdab")
            app[-1] = index
            factory = bytearray(b"\xff" * 0x10000) + app
            factory[0] = 0xe9
            def entry(name, data):
                filename = f"{board}/{name}.bin"
                (self.root / filename).write_bytes(data)
                return dict(filename=filename, size=len(data), sha256=hashlib.sha256(data).hexdigest())
            images[board] = dict(chip="esp32s3", **entry("test.app", app), factory=entry("test.factory", factory))
        self.descriptor = dict(schema=2, firmware="test", images=images)
        self.save()

    def save(self):
        self.manifest.write_text(json.dumps(self.descriptor))


class FirmwareBundleTests(BundleFixture, unittest.TestCase):
    def test_complete_bundle_retains_all_app_and_factory_images(self):
        release = stage_release(self.manifest, self.root / "staged")
        self.assertEqual({t.board for t in release.targets}, set(BOARD_CODES))
        for board in BOARD_CODES:
            self.assertEqual(release.select(board, factory=True).data[0x10000:], release.select(board).data)
        with patch("wits_keyboard.firmware_bundle.frozen", return_value=True), patch("sys._MEIPASS", str(self.root), create=True):
            self.assertIsNone(bundled_manifest())
        (self.root / "staged").rename(self.root / "firmware")
        with patch("wits_keyboard.firmware_bundle.frozen", return_value=True), patch("sys._MEIPASS", str(self.root), create=True):
            self.assertEqual(bundled_manifest(), self.root / "firmware/release.ota.json")

    def test_corrupt_or_missing_model_causes_no_partial_bundle(self):
        app = self.root / self.descriptor["images"]["tqtpro"]["filename"]
        app.write_bytes(b"x" * 400)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            stage_release(self.manifest, self.root / "staged")
        self.assertFalse((self.root / "staged").exists())
        del self.descriptor["images"]["tqtpro"]
        self.save()
        with self.assertRaisesRegex(ValueError, "all three"):
            stage_release(self.manifest, self.root / "staged")

    def test_factory_and_app_must_match_even_with_valid_individual_hashes(self):
        descriptor = self.descriptor["images"]["tqtpro"]["factory"]
        factory = self.root / descriptor["filename"]
        data = factory.read_bytes()[:-1] + b"x"
        factory.write_bytes(data)
        descriptor["sha256"] = hashlib.sha256(data).hexdigest()
        self.save()
        with self.assertRaisesRegex(ValueError, "Factory/app"):
            stage_release(self.manifest, self.root / "staged")


try:
    from PySide6.QtWidgets import QApplication
    from wits_keyboard.firmware_dialog import FirmwareDialog
    from wits_keyboard.usb_flash_dialog import UsbFlashDialog
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False


@unittest.skipUnless(QT_AVAILABLE, "Qt not installed")
class IncludedFirmwareUiTests(BundleFixture, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_usb_defaults_to_included_release_without_selecting_a_model_or_starting(self):
        with patch("wits_keyboard.usb_flash_dialog.bundled_manifest", return_value=self.manifest):
            dialog = UsbFlashDialog()
        self.assertEqual(dialog.manifest, str(self.manifest))
        self.assertIn("Included firmware test", dialog.description.text())
        self.assertIsNone(dialog.model.currentData())
        self.assertFalse(dialog._busy())
        dialog.close()

    def test_ota_defaults_to_included_release_without_starting_an_upload(self):
        runner = Mock()
        with patch("wits_keyboard.firmware_dialog.bundled_manifest", return_value=self.manifest):
            dialog = FirmwareDialog(runner, Mock(), "A")
        self.assertEqual(dialog.image.version, "test")
        self.assertTrue(dialog.upload.isEnabled())
        self.assertIn("Included firmware test", dialog.image_label.text())
        runner.submit.assert_not_called()
        dialog.close()
