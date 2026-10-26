import asyncio
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from wits_keyboard.controller import DiscoveredBoard, KeyboardController

try:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QMessageBox
    from wits_keyboard.app import MainWindow
    QT = True
except ImportError:
    QT = False


class ControllerRemoveTests(unittest.IsolatedAsyncioTestCase):
    async def test_remove_disconnects_forgets_the_pairing_and_drops_the_board(self):
        controller = KeyboardController(lambda *a: None)
        controller.known_devices["A"] = DiscoveredBoard("A", "Board A")
        controller.devices["A"] = object()
        session = MagicMock()
        session.disconnect = AsyncMock()
        controller.sessions["A"] = session
        controller._forget_os_bond = AsyncMock(return_value="Removed the pairing.")
        self.assertEqual(await controller.remove("A"), "Removed the pairing.")
        session.disconnect.assert_awaited_once()
        self.assertNotIn("A", controller.known_devices)
        self.assertNotIn("A", controller.devices)
        self.assertNotIn("A", controller.sessions)
        self.assertNotIn("A", controller.reconnector.enabled)

    async def test_a_board_that_is_off_is_still_removed_with_a_note(self):
        controller = KeyboardController(lambda *a: None)
        controller.known_devices["A"] = DiscoveredBoard("A", "Board A")
        controller._forget_os_bond = AsyncMock(side_effect=RuntimeError("Saved board is not available"))
        note = await controller.remove("A")
        self.assertIn("Bluetooth settings", note)
        self.assertNotIn("A", controller.known_devices)

    async def test_windows_uses_the_windows_unpair_call_without_needing_the_board(self):
        controller = KeyboardController(lambda *a: None)
        with patch.object(sys, "platform", "win32"), \
                patch("wits_keyboard.pairing_windows.unpair_windows", AsyncMock(return_value="gone")) as unpair:
            self.assertEqual(await controller._forget_os_bond("AA:BB:CC:DD:EE:FF"), "gone")
        unpair.assert_awaited_once_with("AA:BB:CC:DD:EE:FF")


@unittest.skipUnless(QT, "Qt not installed")
class WindowRemoveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_removing_a_board_clears_it_from_the_list_and_the_saved_settings(self):
        with tempfile.TemporaryDirectory() as d:
            settings = QSettings(str(Path(d) / "s.ini"), QSettings.Format.IniFormat)
            with patch("wits_keyboard.app.AsyncRunner"), patch("wits_keyboard.app.QSettings", return_value=settings):
                window = MainWindow()
            window._add_or_update_device(DiscoveredBoard("A", "Board A"))
            window._add_or_update_device(DiscoveredBoard("B", "Board B"))
            window.auto_connect_preferences.add("A")
            settings.setValue("aliases/A", "Mine")
            window._board_removed("A", "Mine", "Removed the pairing.")
            self.assertNotIn("A", window.items)
            self.assertEqual(window.device_tree.topLevelItemCount(), 1)
            self.assertNotIn("A", window.auto_connect_preferences)
            self.assertFalse(settings.contains("aliases/A"))
            self.assertIn("Board B", window.items["B"].text(1))
            window.close()

    def test_declining_the_confirmation_removes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            settings = QSettings(str(Path(d) / "s.ini"), QSettings.Format.IniFormat)
            with patch("wits_keyboard.app.AsyncRunner"), patch("wits_keyboard.app.QSettings", return_value=settings):
                window = MainWindow()
            window._add_or_update_device(DiscoveredBoard("A", "Board A"))
            window.items["A"].setSelected(True)
            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
                window._remove_selected()
            window.runner.submit.assert_not_called()
            self.assertIn("A", window.items)
            window.close()


if __name__ == "__main__":
    unittest.main()
