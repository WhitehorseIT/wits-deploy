import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication
    from wits_keyboard.firmware_dialog import FirmwareDialog
    from wits_keyboard.online_release import SignedRelease
    AVAILABLE = True
except ImportError:
    AVAILABLE = False


@unittest.skipUnless(AVAILABLE, "Qt not installed")
class FirmwareDialogOnlineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make(self, release):
        with patch("wits_keyboard.firmware_dialog.bundled_manifest", return_value=None):
            return FirmwareDialog(MagicMock(), MagicMock(), "A", "Board A", signed_release=release)

    def test_download_button_only_appears_for_a_verified_release_with_firmware(self):
        self.assertTrue(self.make(None).download.isHidden())
        self.assertTrue(self.make(SignedRelease("0.2.0", None, {"linux-x86_64": {}})).download.isHidden())
        dialog = self.make(SignedRelease("0.2.0", None, {"firmware": {}}))
        self.assertFalse(dialog.download.isHidden())
        self.assertIn("0.2.0", dialog.download.text())

    def test_failed_download_changes_nothing_and_reenables_the_button(self):
        dialog = self.make(SignedRelease("0.2.0", None, {"firmware": {}}))
        dialog.download.setEnabled(False)
        dialog._downloaded(None, "offline")
        self.assertTrue(dialog.download.isEnabled())
        self.assertIsNone(dialog.image)
        self.assertIn("nothing was changed", dialog.status.text())


if __name__ == "__main__":
    unittest.main()
