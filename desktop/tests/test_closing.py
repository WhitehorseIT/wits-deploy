import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from wits_keyboard.app import ClosingNotice, MainWindow, SHUTDOWN_TIMEOUT_S
    AVAILABLE = True
except ImportError:
    AVAILABLE = False


@unittest.skipUnless(AVAILABLE, "Qt not installed")
class ClosingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self, directory):
        settings = QSettings(str(Path(directory) / "s.ini"), QSettings.Format.IniFormat)
        with patch("wits_keyboard.app.AsyncRunner"), patch("wits_keyboard.app.QSettings", return_value=settings):
            return MainWindow()

    def test_nothing_connected_closes_at_once_without_a_notice(self):
        with tempfile.TemporaryDirectory() as d:
            window = self.make_window(d)
            started = time.monotonic()
            window.close()
            self.assertLess(time.monotonic() - started, 0.3)
            self.assertFalse(window.closing_notice_shown)
            window.runner.close.assert_called_once()

    def test_a_slow_disconnect_keeps_the_window_responsive_and_explains_the_wait(self):
        with tempfile.TemporaryDirectory() as d:
            window = self.make_window(d)
            window.controller.sessions = {"A": SimpleNamespace(state=SimpleNamespace(connected=True))}
            window.runner.close.side_effect = lambda controller: time.sleep(0.9)
            ticks = []
            from PySide6.QtCore import QTimer
            timer = QTimer()
            timer.timeout.connect(lambda: ticks.append(1))
            timer.start(50)
            window.close()
            timer.stop()
            self.assertTrue(window.closing_notice_shown)
            self.assertGreater(len(ticks), 5)  # the event loop kept running during the wait

    def test_a_fast_disconnect_shows_no_notice(self):
        with tempfile.TemporaryDirectory() as d:
            window = self.make_window(d)
            window.controller.sessions = {"A": SimpleNamespace(state=SimpleNamespace(connected=True))}
            window.runner.close.side_effect = lambda controller: time.sleep(0.05)
            window.close()
            self.assertFalse(window.closing_notice_shown)

    def test_countdown_text_counts_down_and_says_the_wait_is_intentional(self):
        notice = ClosingNotice()
        self.assertIn(f"{SHUTDOWN_TIMEOUT_S} second", notice.label.text())
        self.assertIn("intentional", notice.label.text())
        for _ in range(10):
            notice._tick()
        self.assertIn(f"{SHUTDOWN_TIMEOUT_S - 1} second", notice.label.text())
        notice.timer.stop()


if __name__ == "__main__":
    unittest.main()
