import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from wits_keyboard import runtime
from wits_keyboard import launcher


class RuntimeTests(unittest.TestCase):
    def test_source_usb_command_uses_python_module(self):
        with patch.object(runtime, "frozen", return_value=False):
            command = runtime.worker_command("usb-flash", "--port", "port with spaces")
        self.assertEqual(command[1:4], ["-u", "-m", "wits_keyboard.usb_flash"])
        self.assertEqual(command[-1], "port with spaces")

    def test_frozen_gui_and_helper_resolve_the_same_usb_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "bundle with spaces"
            suffix = ".exe" if runtime.sys.platform == "win32" else ""
            helper = root / "helpers" / runtime.WORKER_NAME / (runtime.WORKER_NAME + suffix)
            helper.parent.mkdir(parents=True)
            helper.touch()
            with patch.object(runtime, "frozen", return_value=True):
                for executable in (root / ("WITS-Deploy" + suffix), helper):
                    with patch.object(runtime.sys, "executable", str(executable)):
                        self.assertEqual(runtime.app_directory(), root)
                        self.assertEqual(runtime.worker_command("esptool", "--help"), [str(helper), "esptool", "--help"])

    def test_missing_frozen_helper_fails_instead_of_reopening_the_gui(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(runtime, "frozen", return_value=True), patch.object(runtime.sys, "executable", str(Path(directory)/"WITS-Deploy")):
                with self.assertRaisesRegex(RuntimeError, "complete WITS Deploy package"):
                    runtime.worker_command("usb-flash")

    def test_frozen_logs_use_writable_user_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(runtime, "frozen", return_value=True), patch.dict(os.environ, {"XDG_STATE_HOME": str(root), "LOCALAPPDATA": str(root)}):
                path = runtime.log_directory()
                self.assertTrue(path.is_relative_to(root))
                self.assertEqual(path.name, "logs")
                self.assertNotEqual(path.parent, runtime.app_directory())


class LauncherTests(unittest.TestCase):
    def test_shortcut_defaults_to_menu_without_enabling_autostart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {"XDG_DATA_HOME": str(root/"data"), "XDG_CONFIG_HOME": str(root/"config")}), patch.object(launcher.sys, "platform", "linux"), patch.object(launcher.sys, "argv", ["install"]):
                self.assertEqual(launcher.main(), 0)
            menu = root/"data/applications"/launcher.FILENAME
            self.assertIn("Terminal=false", menu.read_text())
            self.assertFalse((root/"config/autostart"/launcher.FILENAME).exists())

    def test_autostart_is_explicit_and_can_be_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {"XDG_DATA_HOME": str(root/"data"), "XDG_CONFIG_HOME": str(root/"config")}), patch.object(launcher.sys, "platform", "linux"):
                with patch.object(launcher.sys, "argv", ["install", "--autostart"]):
                    launcher.main()
                startup = root/"config/autostart"/launcher.FILENAME
                self.assertTrue(startup.is_file())
                with patch.object(launcher.sys, "argv", ["install", "--remove-autostart"]):
                    launcher.main()
                self.assertFalse(startup.exists())

    def test_launch_path_is_quoted_without_a_shell_command_string(self):
        with patch.object(launcher, "frozen", return_value=True), patch.object(launcher, "app_directory", return_value=Path('/tmp/my app $HOME;test')):
            entry = launcher.desktop_entry()
        self.assertIn("WITS-Deploy", entry)
        self.assertNotIn("sh -c", entry)
        self.assertNotIn("bash -c", entry)
        with self.assertRaises(ValueError):
            launcher.quote_argument("folder\nExec=malicious")
