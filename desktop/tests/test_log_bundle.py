import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from wits_keyboard import log_bundle

try:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from wits_keyboard.app import MainWindow
    QT = True
except ImportError:
    QT = False


class BundleTests(unittest.TestCase):
    def test_bundle_holds_events_logs_traces_and_system_details(self):
        with tempfile.TemporaryDirectory() as d:
            logs = Path(d) / "logs"
            logs.mkdir()
            (logs / "wits-keyboard-debug.log").write_text("current\n")
            (logs / "wits-keyboard-debug.log.1").write_text("older\n")
            (logs / "crash-traces.log").write_text("--- started ---\n")
            (logs / "unrelated.txt").write_text("do not include")
            out = log_bundle.build_bundle(Path(d) / "out.zip", ["first", "second"], logs)
            with zipfile.ZipFile(out) as bundle:
                names = sorted(bundle.namelist())
                self.assertEqual(names, ["crash-traces.log", "event-log.txt", "system.txt",
                                         "wits-keyboard-debug.log", "wits-keyboard-debug.log.1"])
                self.assertEqual(bundle.read("event-log.txt").decode(), "first\nsecond\n")
                self.assertIn("WITS Deploy", bundle.read("system.txt").decode())

    def test_missing_logs_still_produce_a_bundle(self):
        with tempfile.TemporaryDirectory() as d:
            out = log_bundle.build_bundle(Path(d) / "out.zip", [], Path(d) / "nowhere")
            with zipfile.ZipFile(out) as bundle:
                self.assertEqual(sorted(bundle.namelist()), ["event-log.txt", "system.txt"])


@unittest.skipUnless(QT, "Qt not installed")
class LogButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self, d):
        settings = QSettings(str(Path(d) / "s.ini"), QSettings.Format.IniFormat)
        with patch("wits_keyboard.app.AsyncRunner"), patch("wits_keyboard.app.QSettings", return_value=settings):
            return MainWindow()

    def test_copy_puts_the_events_on_the_clipboard_oldest_first(self):
        with tempfile.TemporaryDirectory() as d:
            window = self.make_window(d)
            window.event_log.clear()
            for text in ("one", "two", "three"):
                window._log(text)
            window._copy_log()
            self.assertEqual(QApplication.clipboard().text(), "one\ntwo\nthree")
            window.close()

    def test_save_writes_a_zip_where_the_user_chose(self):
        with tempfile.TemporaryDirectory() as d:
            window = self.make_window(d)
            window.event_log.clear()
            window._log("an event")
            target = str(Path(d) / "mine.zip")
            with patch("wits_keyboard.file_choice.choose_save_path", return_value=target):
                window._save_logs()
            with zipfile.ZipFile(target) as bundle:
                self.assertIn("an event", bundle.read("event-log.txt").decode())
            with patch("wits_keyboard.file_choice.choose_save_path", return_value=""):
                window._save_logs()  # cancel does nothing
            window.close()


if __name__ == "__main__":
    unittest.main()
