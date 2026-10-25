import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from wits_keyboard import release_check as rc
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

    def test_release_json(self):
        data = {"tag_name": "v0.2.0", "body": "Notes\nCritical-below: 0.1.1\n"}
        self.assertEqual(rc.from_release_json(data), Latest("0.2.0", "0.1.1"))
        self.assertEqual(rc.from_release_json({"tag_name": "v0.3.0", "body": None}), Latest("0.3.0"))
        self.assertIsNone(rc.from_release_json({"tag_name": "nightly"}))

    def test_release_list_picks_the_highest_non_draft_including_prereleases(self):
        releases = [{"tag_name": "v0.2.0-dev18", "prerelease": True},
                    {"tag_name": "v0.3.0", "draft": True},
                    {"tag_name": "v0.2.0-dev19", "prerelease": True, "body": "Critical-below: 0.2.0-dev17"}]
        self.assertEqual(rc.from_release_list(releases), Latest("0.2.0-dev19", "0.2.0-dev17"))
        self.assertIsNone(rc.from_release_list([]))
        self.assertIsNone(rc.from_release_list({"message": "rate limited"}))

    def test_newest_keeps_highest_and_strictest(self):
        merged = rc.newest(Latest("0.2.0-dev18"), Latest("0.2.0", "0.1.0"), None)
        self.assertEqual(merged, Latest("0.2.0", "0.1.0"))

    def test_fetch_failure_and_opt_out_return_none(self):
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertIsNone(rc.fetch_latest())
        with patch.dict(os.environ, {rc.DISABLE_ENV: "1"}), patch("urllib.request.urlopen") as opened:
            self.assertIsNone(rc.fetch_latest())
        opened.assert_not_called()


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
            window._latest_release_known(Latest("0.2.0", "0.2.0-dev17"))
            self.assertEqual(color(), "#8a6500")  # dev17 meets the floor, so only an update
            window._latest_release_known(Latest("0.2.1", "0.2.0-dev18"))
            self.assertEqual(color(), "#a71927")
            self.assertEqual(window.items["A"].foreground(5).color().name(), "#ffffff")
            window._show_firmware("A", "unknown")
            self.assertEqual(window.items["A"].text(5), "unknown")
            window.close()


if __name__ == "__main__":
    unittest.main()
