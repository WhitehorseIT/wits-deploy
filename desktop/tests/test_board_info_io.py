import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from wits_keyboard import protocol
from wits_keyboard.storage_stats import summarize

BASE = {"schema": 1, "firmware": "0.2.0-dev14", "board": "waveshare147", "supported": True,
        "present": True, "exported": True, "writable": True, "ejected": False,
        "error": False, "bytes": 32010928128}
IO = {"rb": 0, "wb": 0, "rc": 0, "wc": 0, "mx": 0, "rt": 0, "wt": 0, "ru": 0, "wu": 0, "sl": 0, "er": 0}


def info(**changes):
    return json.dumps({**BASE, **changes}, separators=(",", ":")).encode()


class ParseTests(unittest.TestCase):
    def test_older_firmware_without_io_still_parses(self):
        parsed = protocol.parse_board_info(info())
        self.assertIsNone(parsed.io)
        self.assertEqual(parsed.board, "waveshare147")

    def test_io_counters_are_accepted(self):
        counters = {**IO, "wb": 67108864, "wc": 16384, "mx": 4096, "wt": 140_000_000, "wu": 130_000_000}
        parsed = protocol.parse_board_info(info(io=counters))
        self.assertEqual(parsed.io["wb"], 67108864)

    def test_malformed_io_is_rejected(self):
        for bad in ({**IO, "rb": -1}, {**IO, "rb": "1"}, {**IO, "rb": True}, {**IO, "rb": 1 << 64},
                    {k: v for k, v in IO.items() if k != "er"}, {**IO, "extra": 1}, [1, 2], "x"):
            with self.subTest(bad=bad), self.assertRaises(protocol.ProtocolError):
                protocol.parse_board_info(info(io=bad))

    def test_largest_message_the_firmware_can_send_stays_under_the_limit(self):
        biggest = {key: (1 << 64) - 1 if key in ("rb", "wb", "rt", "wt", "ru", "wu") else (1 << 32) - 1
                   for key in IO}
        message = info(firmware="0.2.0-dev14-" + "x" * 11, io=biggest, bytes=(1 << 63) - 1)
        self.assertLessEqual(len(message), 512)
        protocol.parse_board_info(message)


class SummaryTests(unittest.TestCase):
    def test_write_summary_reports_rate_request_size_and_sd_share(self):
        before = {**IO}
        after = {**IO, "wb": 4 * 1048576, "wc": 1024, "mx": 4096, "wt": 8_000_000, "wu": 7_000_000, "sl": 35}
        text = summarize(before, after)
        self.assertIn("write 0.50 MB/s while busy", text)
        self.assertIn("avg 4.0 KiB per request", text)
        self.assertIn("88% in the SD card", text)
        self.assertNotIn("read ", text)

    def test_idle_interval_returns_nothing(self):
        self.assertIsNone(summarize(IO, dict(IO)))

    def test_board_restart_makes_the_comparison_meaningless(self):
        self.assertIsNone(summarize({**IO, "wb": 100, "wc": 2, "wt": 10, "wu": 5}, {**IO}))

    def test_missing_samples_return_nothing(self):
        self.assertIsNone(summarize(None, IO))
        self.assertIsNone(summarize(IO, None))

    def test_errors_are_called_out(self):
        text = summarize(IO, {**IO, "rb": 1048576, "rc": 2048, "rt": 1_000_000, "ru": 900_000, "er": 3})
        self.assertIn("read 1.00 MB/s", text)
        self.assertIn("3 I/O error(s)", text)


try:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from wits_keyboard.app import MainWindow
    from wits_keyboard.controller import DiscoveredBoard
    QT = True
except ImportError:
    QT = False


@unittest.skipUnless(QT, "Qt not installed")
class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_status_line_shows_throughput_after_the_second_refresh(self):
        directory = tempfile.TemporaryDirectory(prefix="wits-io-tests-")
        settings = QSettings(str(Path(directory.name) / "s.ini"), QSettings.Format.IniFormat)
        with patch("wits_keyboard.app.AsyncRunner"), patch("wits_keyboard.app.QSettings", return_value=settings):
            window = MainWindow()
        window._add_or_update_device(DiscoveredBoard("A", "Board A"))
        window._board_event("A", "state", {"connected": True, "authenticated": True, "armed": False, "typing": False})
        window.items["A"].setSelected(True)
        base = {"firmware": "0.2.0-dev14", "board": "waveshare147", "supported": True, "present": True,
                "exported": True, "writable": True, "ejected": False, "error": False, "bytes": 1 << 30}
        window._board_event("A", "board_info", {**base, "io": dict(IO)})
        self.assertNotIn("MB/s", window.storage_status_label.text())
        window._board_event("A", "board_info", {**base, "io": {**IO, "wb": 1 << 20, "wc": 256,
                                                                "mx": 4096, "wt": 2_000_000, "wu": 1_900_000}})
        self.assertIn("write 0.50 MB/s while busy", window.storage_status_label.text())
        window._board_event("A", "board_info", {**base, "io": {**IO, "wb": 1 << 20, "wc": 256,
                                                                "mx": 4096, "wt": 2_000_000, "wu": 1_900_000}})
        self.assertIn("write 0.50 MB/s while busy", window.storage_status_label.text())  # idle refresh keeps the last result
        window.close()
        directory.cleanup()


if __name__ == "__main__":
    unittest.main()
