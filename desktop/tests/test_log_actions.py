import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QProcess
    from PySide6.QtWidgets import QApplication, QWidget
    from wits_keyboard import log_actions
    from wits_keyboard.usb_flash_dialog import UsbFlashDialog
    QT = True
except ImportError:
    QT = False


@unittest.skipUnless(QT, "Qt not installed")
class LogActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_copy_and_save_buttons_use_the_current_text(self):
        parent, messages, text = QWidget(), [], ["line one\nline two"]
        row = log_actions.log_buttons(parent, lambda: text[0], "demo", messages.append)
        row.copy_button.click()
        self.assertEqual(QApplication.clipboard().text(), "line one\nline two")
        self.assertIn("Copied 2 lines", messages[-1])
        with tempfile.TemporaryDirectory() as d:
            target = str(Path(d) / "out.txt")
            text[0] = "newer text é"
            with patch("wits_keyboard.file_choice.choose_save_path", return_value=target):
                row.save_button.click()
            self.assertEqual(Path(target).read_text(encoding="utf-8"), "newer text é")
            self.assertIn("Saved to", messages[-1])
            with patch("wits_keyboard.file_choice.choose_save_path", return_value=""):
                row.save_button.click()  # cancel: nothing happens
            self.assertEqual(Path(target).read_text(encoding="utf-8"), "newer text é")

    def test_a_layout_mismatch_selects_the_factory_install_and_explains_it(self):
        with patch("wits_keyboard.usb_flash_dialog.bundled_manifest", return_value=None):
            dialog = UsbFlashDialog()
        self.assertFalse(dialog.mode.currentData())
        dialog.log.setPlainText("ERROR: Board partition layout differs from this release: this board does not have "
                                "the WITS flash layout yet; use factory installation")
        dialog._finished(1, QProcess.ExitStatus.NormalExit)
        self.assertTrue(dialog.mode.currentData())             # factory install selected, not started
        self.assertIn("new or blank", dialog.description.text().replace("it is new, blank", "new or blank"))
        self.assertTrue(dialog.flash.isEnabled())
        dialog.deleteLater()

    def test_other_failures_leave_the_mode_alone(self):
        with patch("wits_keyboard.usb_flash_dialog.bundled_manifest", return_value=None):
            dialog = UsbFlashDialog()
        dialog.log.setPlainText("ERROR: Failed to connect to ESP32-S3")
        dialog._finished(1, QProcess.ExitStatus.NormalExit)
        self.assertFalse(dialog.mode.currentData())
        dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
