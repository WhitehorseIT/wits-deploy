import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QHeaderView
    from wits_keyboard.app import MainWindow
    from wits_keyboard.controller import DiscoveredBoard
    AVAILABLE = True
except ImportError:
    AVAILABLE = False

TARGET, DEVICE, STATE, RESULT, AUTO = range(5)


@unittest.skipUnless(AVAILABLE, "Qt not installed")
class DeviceListLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="wits-layout-tests-")
        settings = QSettings(str(Path(self.directory.name) / "settings.ini"), QSettings.Format.IniFormat)
        self.patches = [patch("wits_keyboard.app.AsyncRunner"), patch("wits_keyboard.app.QSettings", return_value=settings)]
        for item in self.patches:
            item.start()
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        for item in self.patches:
            item.stop()
        self.directory.cleanup()

    def test_auto_connect_sits_beside_target_and_stays_visible_in_a_narrow_list(self):
        tree = self.window.device_tree
        header = tree.header()
        self.assertEqual(header.visualIndex(TARGET), 0)
        self.assertEqual(header.visualIndex(AUTO), 1)
        self.assertEqual(header.visualIndex(RESULT), tree.columnCount() - 1)
        self.assertEqual(header.sectionResizeMode(AUTO), QHeaderView.ResizeMode.ResizeToContents)
        self.window._add_or_update_device(DiscoveredBoard("A", "A very long board name " * 4))
        tree.resize(420, 200)
        tree.show()
        self.app.processEvents()
        edge = tree.columnViewportPosition(AUTO) + tree.columnWidth(AUTO)
        self.assertLessEqual(edge, tree.viewport().width())


if __name__ == "__main__":
    unittest.main()
