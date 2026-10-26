import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from wits_keyboard import release_check as rc
from wits_keyboard.online_release import SignedRelease
from wits_keyboard.release_check import Latest

try:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from wits_keyboard.app import MainWindow
    from wits_keyboard.controller import DiscoveredBoard
    QT = True
except ImportError:
    QT = False


class VersionTests(unittest.TestCase):
    def test_ordering(self):
        order = ["0.1.0", "0.2.0-dev9", "0.2.0-dev18", "0.2.0-rc1", "0.2.0", "0.2.1"]
        keys = [rc.parse_version(v) for v in order]
        self.assertEqual(keys, sorted(keys))
        self.assertIsNone(rc.parse_version("garbage"))

    def test_classify(self):
        latest = Latest("0.2.0-dev18")
        self.assertEqual(rc.classify("0.2.0-dev18", latest), rc.CURRENT)
        self.assertEqual(rc.classify("0.2.0-dev17", latest), rc.UPDATE)
        self.assertEqual(rc.classify("0.2.0-dev19", latest), rc.CURRENT)  # newer than known
        self.assertIsNone(rc.classify("?", latest))
        self.assertIsNone(rc.classify("0.2.0", None))

    def test_critical_threshold(self):
        latest = Latest("0.2.0", critical_below="0.2.0-dev15")
        self.assertEqual(rc.classify("0.2.0-dev14", latest), rc.CRITICAL)
        self.assertEqual(rc.classify("0.2.0-dev15", latest), rc.UPDATE)

    def test_newest_from_tags_keeps_the_streams_apart(self):
        tags = ["v0.2.0-dev22", "fw-v1.0.0-rc1", "v0.2.0-dev18", "fw-v0.2.0", "nightly", "fw-vjunk", "v0.3.0-draftish"]
        self.assertEqual(rc.newest_from_tags(tags, "v"), Latest("0.2.0-dev22"))
        self.assertEqual(rc.newest_from_tags(tags, "fw-v"), Latest("1.0.0-rc1"))
        self.assertIsNone(rc.newest_from_tags(["nightly"], "v"))
        self.assertIsNone(rc.newest_from_tags([], "fw-v"))

    def test_newest_keeps_highest_and_strictest(self):
        merged = rc.newest(Latest("0.2.0-dev18"), Latest("0.2.0", "0.1.0"), None)
        self.assertEqual(merged, Latest("0.2.0", "0.1.0"))

    def test_opt_out_makes_no_request(self):
        from wits_keyboard import online_release
        with patch.dict(os.environ, {rc.DISABLE_ENV: "1"}):
            opened = MagicMock()
            self.assertIsNone(online_release.fetch_listing(opened))
            self.assertIsNone(online_release.latest_signed(opened, tags=None))
        opened.assert_not_called()


def result(firmware_tag, signed_firmware, app_tag=None, signed_app=None):
    return {"firmware": (firmware_tag, signed_firmware), "app": (app_tag, signed_app)}


@unittest.skipUnless(QT, "Qt not installed")
class ColumnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_colors_follow_status(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = QSettings(str(Path(directory) / "s.ini"), QSettings.Format.IniFormat)
            with patch("wits_keyboard.app.AsyncRunner"), patch("wits_keyboard.app.QSettings", return_value=settings):
                window = MainWindow()
            window.latest_firmware = Latest("0.2.0-dev18")
            window._add_or_update_device(DiscoveredBoard("A", "A"))
            color = lambda: window.items["A"].background(5).color().name()
            window._show_firmware("A", "0.2.0-dev18")
            self.assertEqual(color(), "#145c43")
            window._show_firmware("A", "0.2.0-dev17")
            self.assertEqual(color(), "#8a6500")
            window._latest_release_known(result(Latest("0.2.0"), SignedRelease("0.2.0", "0.2.0-dev17", {}, "firmware")))
            self.assertEqual(color(), "#8a6500")  # dev17 meets the floor, so only an update
            window._latest_release_known(result(Latest("0.2.1"), SignedRelease("0.2.1", "0.2.0-dev18", {"firmware": {}}, "firmware")))
            self.assertEqual(window.signed_firmware.version, "0.2.1")
            window._latest_release_known(result(Latest("0.2.1"), None))  # unsigned: keeps the earlier verified release
            self.assertEqual(color(), "#a71927")
            self.assertEqual(window.items["A"].foreground(5).color().name(), "#ffffff")
            window._show_firmware("A", "unknown")
            self.assertEqual(window.items["A"].text(5), "unknown")
            window.close()


if __name__ == "__main__":
    unittest.main()
