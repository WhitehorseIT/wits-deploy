import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtWidgets import QApplication, QHeaderView
    from wits_keyboard.app import MainWindow
    from wits_keyboard.controller import DiscoveredBoard
    AVAILABLE = True
except ImportError:
    AVAILABLE = False

TARGET, DEVICE, STATE, RESULT, AUTO, FIRMWARE = range(6)


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

    def test_firmware_column_sits_between_state_and_result_and_shows_the_version(self):
        tree = self.window.device_tree
        header = tree.header()
        self.assertEqual(header.visualIndex(FIRMWARE), header.visualIndex(STATE) + 1)
        self.assertEqual(header.visualIndex(RESULT), header.visualIndex(FIRMWARE) + 1)
        self.assertEqual(header.sectionResizeMode(FIRMWARE), QHeaderView.ResizeMode.Interactive)
        self.window._add_or_update_device(DiscoveredBoard("A", "Board A"))
        self.window._board_event("A", "board_info", {"firmware": "0.2.0-dev18", "board": "tqtpro"})
        self.assertEqual(self.window.items["A"].text(FIRMWARE), "0.2.0-dev18")

    def test_every_state_gets_an_opaque_badge_and_the_cell_text_stays_hidden(self):
        self.window._add_or_update_device(DiscoveredBoard("A", "Board A"))
        for label in ("Watching", "Offline", "Discovered", "DISARMED", "Something new"):
            self.window._set_board_status("A", label)
            item = self.window.items["A"]
            badge = self.window.device_tree.itemWidget(item, STATE)
            self.assertEqual(item.text(STATE), label)                          # logic still reads the text
            self.assertEqual(item.foreground(STATE).color().alpha(), 0)       # but it is not drawn under the badge
            self.assertNotIn("palette(", badge.styleSheet().split("border")[0])  # opaque colors, not theme lookups

    def test_boards_are_on_top_at_full_width_with_every_control_visible(self):
        window = self.window
        window.resize(1180, 940)
        window.show()
        self.app.processEvents()
        splitter = window.main_splitter
        self.assertEqual(splitter.orientation(), Qt.Orientation.Vertical)
        self.assertTrue(splitter.widget(0).isAncestorOf(window.device_tree))
        self.assertGreater(window.device_tree.width(), window.width() * 0.9)
        for button in (window.scan_button, window.connect_button, window.repair_button,
                       window.disconnect_button, window.storage_refresh_button,
                       window.storage_readonly_button, window.storage_writable_button):
            self.assertTrue(button.isVisible())
            self.assertGreater(button.width(), 0)

    def test_special_keys_sit_beside_the_text_box(self):
        window = self.window
        window.resize(1180, 940)
        window.show()
        self.app.processEvents()
        editor_right = window.text_editor.mapTo(window, window.text_editor.rect().topRight()).x()
        key_left = window.key_buttons[0].mapTo(window, window.key_buttons[0].rect().topLeft()).x()
        self.assertGreater(key_left, editor_right)

    def test_splitter_position_is_remembered(self):
        self.window.main_splitter.setSizes([400, 400])
        self.window._save_splitter_sizes()
        self.assertEqual(self.window._saved_splitter_sizes(), self.window.main_splitter.sizes())

    def test_text_box_is_as_tall_as_the_special_keys(self):
        window = self.window
        window.resize(1180, 940)
        window.show()
        self.app.processEvents()
        editor_group = window.text_editor.parentWidget()
        key_group = window.key_buttons[0].parentWidget()
        self.assertLessEqual(abs(editor_group.height() - key_group.height()), 2)


if __name__ == "__main__":
    unittest.main()
