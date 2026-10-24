import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtWidgets import QApplication
    from wits_keyboard.app import MainWindow
    from wits_keyboard.controller import DiscoveredBoard
    from wits_keyboard import protocol
    AVAILABLE = True
except ImportError:
    AVAILABLE = False


@unittest.skipUnless(AVAILABLE, "Qt not installed")
class DeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="wits-delay-tests-")
        self.settings = QSettings(str(Path(self.directory.name) / "settings.ini"), QSettings.Format.IniFormat)
        self.runner_patch = patch("wits_keyboard.app.AsyncRunner")
        self.settings_patch = patch("wits_keyboard.app.QSettings", return_value=self.settings)
        self.runner_patch.start()
        self.settings_patch.start()
        self.window = MainWindow()
        self.submissions = []
        def submit(coroutine, *args, **kwargs):
            self.submissions.append((coroutine.cr_code.co_name, dict(coroutine.cr_frame.f_locals)))
            coroutine.close()
        self.window.runner.submit.side_effect = submit
        for address in ("A", "B"):
            self.window._add_or_update_device(DiscoveredBoard(address, f"Board {address}"))
            self.window._board_event(address, "state", {
                "connected": True, "authenticated": True, "armed": True, "typing": False,
            })
        self.window.items["A"].setCheckState(0, Qt.CheckState.Checked)
        self.window.start_delay.setValue(5)
        self.window.text_editor.setPlainText("Sample-123")

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.settings_patch.stop()
        self.runner_patch.stop()
        self.directory.cleanup()

    def expire(self):
        self.window.pending_delivery.deadline = 0
        self.window._delivery_tick()

    def test_countdown_sends_nothing_early_and_keeps_original_targets_text_and_speed(self):
        self.window.character_delay.setValue(500)
        self.window._send_text()
        self.assertFalse(self.submissions)
        self.assertIn("Board A", self.window.delivery_status_label.text())
        self.window.items["A"].setCheckState(0, Qt.CheckState.Unchecked)
        self.window.items["B"].setCheckState(0, Qt.CheckState.Checked)
        self.window.text_editor.setPlainText("New draft")
        self.expire()
        operation, values = self.submissions[0]
        self.assertEqual(operation, "send_text_many")
        self.assertEqual(values["addresses"], ["A"])
        self.assertEqual(values["text"], "Sample-123")
        self.assertEqual(values["key_interval_ms"], 500)
        self.assertEqual(self.window.text_editor.toPlainText(), "New draft")

    def test_storage_controls_require_one_supported_disarmed_ejected_board(self):
        item = self.window.items["A"]
        item.setSelected(True)
        value = dict(firmware="0.2.0-dev", board="waveshare7", supported=True,
                     present=True, exported=False, writable=False, ejected=True,
                     error=False, bytes=1024 * 1024)
        self.window._board_event("A", "board_info", value)
        self.assertFalse(self.window.storage_writable_button.isEnabled()) # Armed.
        self.window._board_event("A", "state", {
            "connected": True, "authenticated": True, "armed": False, "typing": False,
        })
        self.assertTrue(self.window.storage_writable_button.isEnabled())
        self.assertIn("0.2.0-dev", self.window.storage_status_label.text())
        self.window._board_event("A", "board_info", {**value, "exported": True})
        self.assertFalse(self.window.storage_writable_button.isEnabled())
        self.window._board_event("A", "board_info", {**value, "supported": False})
        self.assertFalse(self.window.storage_readonly_button.isEnabled())
        self.window._board_event("A", "board_info", value)
        self.window.items["B"].setSelected(True)
        self.assertFalse(self.window.storage_writable_button.isEnabled())

    def test_storage_disconnect_discards_cached_permission(self):
        self.window.items["A"].setSelected(True)
        self.window._board_event("A", "board_info", {
            "firmware": "0.2.0-dev", "supported": True, "present": True,
            "exported": False, "writable": False, "bytes": 1024,
        })
        self.window._board_event("A", "state", {"connected": False})
        self.assertNotIn("A", self.window.board_information)
        self.assertFalse(self.window.storage_refresh_button.isEnabled())

    def test_storage_actions_target_highlighted_row_instead_of_checked_targets(self):
        self.window.items["B"].setSelected(True)
        self.window._storage_selected(None)
        operation, values = self.submissions[-1]
        self.assertEqual(operation, "read_info")
        self.assertEqual(values["address"], "B")

    def test_disarm_cancels_even_if_board_is_rearmed_before_original_deadline(self):
        self.window._send_text()
        self.window._board_event("A", "state", {"connected": True, "authenticated": True, "armed": False})
        self.window._board_event("A", "state", {"connected": True, "authenticated": True, "armed": True})
        self.window._delivery_tick()
        self.assertIsNone(self.window.pending_delivery)
        self.assertFalse(self.submissions)
        self.assertIn("canceled", self.window.delivery_status_label.text())

    def test_cancel_button_keeps_unsent_editor_content(self):
        self.window._send_text()
        self.window.cancel_delivery_button.click()
        self.assertFalse(self.submissions)
        self.assertIsNone(self.window.pending_delivery)
        self.assertEqual(self.window.text_editor.toPlainText(), "Sample-123")

    def test_stop_all_cancels_countdown_and_only_submits_stop(self):
        self.window._send_text()
        self.window._stop_all()
        self.window._delivery_tick()
        self.assertIsNone(self.window.pending_delivery)
        self.assertEqual([name for name, _ in self.submissions], ["stop_all"])

    def test_special_keys_use_same_start_delay(self):
        self.window._send_key(protocol.KEY_ENTER, 0, "Enter")
        self.assertFalse(self.submissions)
        self.expire()
        operation, values = self.submissions[0]
        self.assertEqual(operation, "key_action")
        self.assertEqual(values["key_code"], protocol.KEY_ENTER)

    def test_zero_start_delay_submits_immediately_and_does_not_log_text(self):
        self.window.start_delay.setValue(0)
        self.window._send_text()
        self.assertIsNone(self.window.pending_delivery)
        self.assertEqual(self.submissions[0][0], "send_text_many")
        messages = [self.window.event_log.item(i).text() for i in range(self.window.event_log.count())]
        self.assertFalse(any("Sample-123" in message for message in messages))

    def test_delay_preferences_are_separate(self):
        self.window.start_delay.setValue(7.5)
        self.window.character_delay.setValue(250)
        self.assertEqual(self.settings.value("sending/start_delay_s", type=float), 7.5)
        self.assertEqual(self.settings.value("sending/character_delay_ms", type=int), 250)

    def test_application_close_cancels_pending_send(self):
        self.window._send_text()
        self.window.close()
        self.window._delivery_tick()
        self.assertIsNone(self.window.pending_delivery)
        self.assertFalse(self.submissions)

    def test_auto_connect_preference_is_independent_of_targets_and_restored(self):
        import json
        self.window.controller.known_devices["A"] = DiscoveredBoard("A", "Board A")
        self.window.items["A"].setCheckState(4, Qt.CheckState.Checked)
        self.assertEqual(self.window.items["A"].checkState(0), Qt.CheckState.Checked)
        self.assertTrue(json.loads(self.settings.value("known_devices"))[0]["auto_connect"])
        restored = MainWindow()
        try:
            self.assertEqual(restored.items["A"].checkState(4), Qt.CheckState.Checked)
            self.assertEqual(restored.items["A"].checkState(0), Qt.CheckState.Unchecked)
            self.assertIn("A", restored.auto_connect_preferences)
        finally:
            restored.close()

    def test_auto_connection_updates_progress_without_targeting_or_arming(self):
        self.window.items["A"].setCheckState(0, Qt.CheckState.Unchecked)
        self.window._board_event("A", "state", {"connected": False})
        self.window._board_event("A", "auto_connect", {"status": "connecting", "message": "Auto-connecting"})
        self.assertIn("A", self.window.management_pending)
        self.window._board_event("A", "state", {"connected": True, "authenticated": True, "armed": False})
        self.window._board_event("A", "auto_connect", {"status": "connected", "message": "Automatically connected"})
        self.assertNotIn("A", self.window.management_pending)
        self.assertEqual(self.window.items["A"].checkState(0), Qt.CheckState.Unchecked)
        self.assertFalse(self.window.states["A"]["armed"])
