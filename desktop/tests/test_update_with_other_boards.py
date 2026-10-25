import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QMessageBox
    from wits_keyboard.app import MainWindow
    from wits_keyboard.controller import DiscoveredBoard, KeyboardController
    AVAILABLE = True
except ImportError:
    AVAILABLE = False

CONNECTED = {"connected": True, "authenticated": True, "armed": False, "typing": False}


@unittest.skipUnless(AVAILABLE, "Qt not installed")
class UpdateWithOtherBoardsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="wits-update-tests-")
        settings = QSettings(str(Path(self.directory.name) / "s.ini"), QSettings.Format.IniFormat)
        self.patches = [patch("wits_keyboard.app.AsyncRunner"), patch("wits_keyboard.app.QSettings", return_value=settings)]
        for item in self.patches:
            item.start()
        self.window = MainWindow()
        self.submissions = []

        def submit(coroutine, on_success=None, on_error=None, *, operation="", on_finished=None):
            self.submissions.append((operation, dict(coroutine.cr_frame.f_locals)))
            coroutine.close()
            if on_finished:
                on_finished()  # the real runner calls this when the coroutine finishes

        self.window.runner.submit.side_effect = submit
        for address in ("A", "B", "C"):
            self.window._add_or_update_device(DiscoveredBoard(address, f"Board {address}"))
        self.window.items["A"].setSelected(True)
        self.dialog_patch = patch("wits_keyboard.firmware_dialog.FirmwareDialog")
        self.dialog = self.dialog_patch.start()

    def tearDown(self):
        self.dialog_patch.stop()
        self.window.close()
        self.app.processEvents()
        for item in self.patches:
            item.stop()
        self.directory.cleanup()

    def connect(self, *addresses):
        for address in addresses:
            self.window._board_event(address, "state", dict(CONNECTED))

    def test_a_single_connected_board_opens_the_updater_without_asking(self):
        self.connect("A")
        with patch.object(QMessageBox, "question") as question:
            self.window._update_firmware()
        question.assert_not_called()
        self.dialog.assert_called_once()
        self.assertEqual(self.dialog.call_args.args[2], "A")
        self.assertEqual(self.submissions, [])

    def test_declining_keeps_the_other_boards_and_does_not_update(self):
        self.connect("A", "B")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as question:
            self.window._update_firmware()
        question.assert_called_once()
        self.dialog.assert_not_called()
        self.assertEqual(self.submissions, [])

    def test_accepting_disconnects_only_the_other_boards_then_opens_the_updater(self):
        self.connect("A", "B", "C")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as question:
            self.window._update_firmware()
        self.assertIn("Board B", question.call_args.args[2])
        self.assertIn("Board C", question.call_args.args[2])
        self.assertNotIn("Board A", question.call_args.args[2])
        operation, values = self.submissions[0]
        self.assertEqual(operation, "disconnect other boards for update")
        self.assertEqual(sorted(values["addresses"]), ["B", "C"])
        self.dialog.assert_called_once()
        self.assertEqual(self.dialog.call_args.args[2], "A")

    def test_other_boards_lose_auto_connect_during_the_update_and_get_it_back(self):
        from PySide6.QtCore import Qt
        self.connect("A", "B", "C")
        for address in ("A", "B"):
            self.window.items[address].setCheckState(4, Qt.CheckState.Checked)
        states = {}

        def during_update(*args, **kwargs):
            states.update({a: self.window.items[a].checkState(4) for a in "ABC"})
            return MagicMock()

        self.dialog.side_effect = during_update
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.window._update_firmware()
        self.assertEqual(states["A"], Qt.CheckState.Checked)      # the updating board keeps its setting
        self.assertEqual(states["B"], Qt.CheckState.Unchecked)    # was ticked, off during the update
        self.assertEqual(states["C"], Qt.CheckState.Unchecked)    # never ticked, stays off
        self.assertEqual(self.window.items["B"].checkState(4), Qt.CheckState.Checked)
        self.assertEqual(self.window.items["C"].checkState(4), Qt.CheckState.Unchecked)
        self.assertIn("B", self.window.auto_connect_preferences)

    def test_a_disconnected_saved_board_does_not_count_as_connected(self):
        self.connect("A")
        self.window._board_event("B", "state", {"connected": False, "authenticated": False, "armed": False, "typing": False})
        with patch.object(QMessageBox, "question") as question:
            self.window._update_firmware()
        question.assert_not_called()
        self.dialog.assert_called_once()


@unittest.skipUnless(AVAILABLE, "Qt not installed")
class DisconnectManyTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_board_is_attempted_even_if_one_fails(self):
        controller = KeyboardController.__new__(KeyboardController)
        calls = []

        async def disconnect(address):
            calls.append(address)
            if address == "B":
                raise RuntimeError("link already gone")

        controller.disconnect = disconnect
        await controller.disconnect_many(["A", "B", "C"])
        self.assertEqual(sorted(calls), ["A", "B", "C"])


if __name__ == "__main__":
    unittest.main()
