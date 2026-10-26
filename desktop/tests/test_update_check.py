import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from wits_keyboard import source_update, update_check_dialog as dialog_module
from wits_keyboard.online_release import SignedRelease
from wits_keyboard.update_check_dialog import plan

try:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from wits_keyboard.app import MainWindow
    QT = True
except ImportError:
    QT = False


def app_release(version, source=True):
    assets = {"source": {"name": "s.zip", "size": 1, "sha256": "0" * 64}} if source else {"linux-x86_64": {}}
    return SignedRelease(version, None, assets, "app")


def snapshot(commit="abcdef1234"):
    return SignedRelease("0.2.0-dev24", None, {"source": {"name": "s.zip", "size": 1, "sha256": "0" * 64}},
                         "source", commit, 9)


def found(app=None, firmware=None, snap=None):
    return {"offline": False, "app": app, "firmware": firmware, "snapshot": snap}


class PlanTests(unittest.TestCase):
    def test_offline_says_so_and_offers_nothing(self):
        result = plan({"offline": True}, False, current_build="1234567")
        self.assertEqual(result.action, "none")
        self.assertIn("Could not reach GitHub", "\n".join(result.lines))

    def test_a_newer_release_is_offered_to_a_launcher_started_source_install(self):
        result = plan(found(app_release("0.2.0-dev25")), False, current_version="0.2.0-dev24", current_build="1234567")
        self.assertEqual(result.action, "source")
        self.assertIn("release 0.2.0-dev25", result.action_text)
        self.assertIn("an update is available", "\n".join(result.lines))

    def test_up_to_date_offers_nothing(self):
        result = plan(found(app_release("0.2.0-dev24")), False, current_version="0.2.0-dev24", current_build="1234567")
        self.assertEqual(result.action, "none")
        self.assertIn("up to date", "\n".join(result.lines))

    def test_snapshots_need_the_checkbox_and_a_different_commit(self):
        result = plan(found(app_release("0.2.0-dev24"), snap=snapshot("ffff0001")), True,
                      current_version="0.2.0-dev24", current_build="1234567")
        self.assertEqual(result.action, "source")
        self.assertIn("snapshot ffff000", result.action_text)
        off = plan(found(app_release("0.2.0-dev24"), snap=snapshot("ffff0001")), False,
                   current_version="0.2.0-dev24", current_build="1234567")
        self.assertEqual(off.action, "none")
        self.assertNotIn("Development snapshot", "\n".join(off.lines))
        same = plan(found(app_release("0.2.0-dev24"), snap=snapshot("1234567abc")), True,
                    current_version="0.2.0-dev24", current_build="1234567")
        self.assertEqual(same.action, "none")

    def test_an_update_that_cannot_be_installed_here_explains_why(self):
        result = plan(found(app_release("0.2.0-dev25")), False, current_version="0.2.0-dev24", current_build="x",
                      source_reason="Start the app with WINDOWS-START.cmd to enable updating from inside the app.")
        self.assertEqual(result.action, "none")
        self.assertIn("WINDOWS-START.cmd", result.note)
        self.assertIn("0.2.0-dev25", result.note)

    def test_the_packaged_linux_build_hands_over_to_the_existing_updater(self):
        reason = lambda release: None
        result = plan(found(app_release("0.2.0-dev25")), False, current_version="0.2.0-dev24", current_build="",
                      app_reason_for=reason)
        self.assertEqual((result.action, result.action_text), ("app", "Update app to 0.2.0-dev25…"))
        blocked = plan(found(app_release("0.2.0-dev25")), False, current_version="0.2.0-dev24", current_build="",
                       app_reason_for=lambda release: "The folder is not writable.")
        self.assertEqual((blocked.action, blocked.note), ("none", "The folder is not writable."))


@unittest.skipUnless(QT, "Qt not installed")
class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make(self, directory):
        settings = QSettings(str(Path(directory) / "s.ini"), QSettings.Format.IniFormat)
        with patch("wits_keyboard.app.AsyncRunner"), patch("wits_keyboard.app.QSettings", return_value=settings):
            return MainWindow(), settings

    def test_a_staged_update_closes_the_app_with_the_update_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            window, _ = self.make(d)
            self.assertEqual(window.requested_exit_code, 0)
            window._restart_for_update()
            self.assertEqual(window.requested_exit_code, source_update.UPDATE_EXIT_CODE)

    def test_an_armed_board_blocks_the_restart_until_it_is_disarmed(self):
        from wits_keyboard.controller import DiscoveredBoard
        from PySide6.QtWidgets import QMessageBox
        with tempfile.TemporaryDirectory() as d:
            window, _ = self.make(d)
            window._add_or_update_device(DiscoveredBoard("A", "Board A"))
            window.states["A"] = {"connected": True, "authenticated": True, "armed": True, "typing": False}
            with patch.object(QMessageBox, "information") as info:
                window._restart_for_update()
            info.assert_called_once()
            self.assertEqual(window.requested_exit_code, 0)

    def test_the_check_button_exists_and_the_dialog_remembers_the_snapshot_choice(self):
        with tempfile.TemporaryDirectory() as d:
            window, settings = self.make(d)
            self.assertEqual(window.check_updates_button.text(), "Check for updates…")
            with patch.object(dialog_module, "gather", return_value={"offline": True}):
                dialog = dialog_module.UpdateCheckDialog(settings, window)
                self.app.processEvents()
                self.assertFalse(dialog.snapshots.isChecked())
                dialog.snapshots.setChecked(True)
                self.assertEqual(str(settings.value(dialog_module.INCLUDE_SNAPSHOTS_KEY)), "true")
                second = dialog_module.UpdateCheckDialog(settings, window)
                self.assertTrue(second.snapshots.isChecked())
                dialog.deleteLater()
                second.deleteLater()


if __name__ == "__main__":
    unittest.main()
