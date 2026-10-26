import hashlib
import io
import os
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from wits_keyboard import app_update
from wits_keyboard.online_release import DOWNLOAD_BASE, SignedRelease
from wits_keyboard.signing import SignatureError

TOP = "WITS-Deploy-0.2.0-dev20-Linux-x86_64"


def make_tar(members=None, top=TOP):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as tar:
        for name, data in (members if members is not None else {f"{top}/WITS-Deploy": b"#!/bin/sh\n"}).items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o755
            tar.addfile(info, io.BytesIO(data))
    return stream.getvalue()


def release_for(archive, version="0.2.0-dev20"):
    return SignedRelease(version, None, {"linux-x86_64": {
        "name": f"WITS-Deploy-{version}-Linux-x86_64.tar.gz", "size": len(archive),
        "sha256": hashlib.sha256(archive).hexdigest()}})


class Net:
    def __init__(self, release, body):
        self.url, self.body = release.asset_url("linux-x86_64"), body

    def __call__(self, request, timeout=0):
        assert request.full_url == self.url
        stream = io.BytesIO(self.body)
        stream.__enter__ = lambda *a: stream
        stream.__exit__ = lambda *a: None
        return stream


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.parent, self.data = Path(self.tmp.name, "Apps"), Path(self.tmp.name, "data")
        self.parent.mkdir()

    def run_download(self, archive, body=None, **kwargs):
        release = release_for(archive)
        return app_update.download_app(release, urlopen=Net(release, archive if body is None else body),
                                       parent=self.parent, directory=self.data, **kwargs)

    def leftovers(self):
        return sorted(p.name for p in self.parent.iterdir())

    def test_verified_archive_is_installed_beside_the_running_copy(self):
        folder = self.run_download(make_tar())
        self.assertEqual(folder, self.parent / TOP)
        self.assertTrue(os.access(folder / "WITS-Deploy", os.X_OK))
        self.assertEqual(self.leftovers(), [TOP])  # no staging folders remain

    def test_tampered_download_is_refused_and_leaves_nothing(self):
        archive = make_tar()
        with self.assertRaises(SignatureError):
            self.run_download(archive, body=make_tar({f"{TOP}/WITS-Deploy": b"evil\n"}))
        self.assertEqual(self.leftovers(), [])

    def test_unsafe_or_misplaced_entries_are_refused(self):
        for members in ({"../escape": b"x", f"{TOP}/WITS-Deploy": b"x"},
                        {"/abs/path": b"x"},
                        {"Other-Folder/WITS-Deploy": b"x"},
                        {f"{TOP}/readme": b"x"}):  # no application inside
            with self.subTest(members=list(members)):
                with self.assertRaises(SignatureError):
                    self.run_download(make_tar(members))
                self.assertEqual(self.leftovers(), [])
                self.assertFalse(Path(self.tmp.name, "escape").exists())

    def test_symlink_escaping_the_folder_is_refused(self):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w:gz") as tar:
            link = tarfile.TarInfo(f"{TOP}/evil")
            link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
            tar.addfile(link)
            info = tarfile.TarInfo(f"{TOP}/WITS-Deploy")
            tar.addfile(info, io.BytesIO(b""))
        with self.assertRaises(SignatureError):
            self.run_download(stream.getvalue())
        self.assertEqual(self.leftovers(), [])

    def test_cancel_stops_the_download(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(InterruptedError):
            self.run_download(make_tar(), cancelled=event)
        self.assertEqual(self.leftovers(), [])

    def test_complete_earlier_attempt_is_reused_and_partial_folder_refused(self):
        archive = make_tar()
        self.run_download(archive)
        release = release_for(archive)
        net = MagicMock(side_effect=AssertionError("must not download again"))
        self.assertEqual(app_update.download_app(release, urlopen=net, parent=self.parent, directory=self.data),
                         self.parent / TOP)
        (self.parent / TOP / "WITS-Deploy").unlink()
        with self.assertRaises(SignatureError):
            app_update.download_app(release, urlopen=net, parent=self.parent, directory=self.data)


@unittest.skipUnless(sys.platform == "linux", "uses /bin/sh")
class RestartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.marker = self.root / "old-ran"

    def program(self, name, body):
        folder = self.root / name
        folder.mkdir()
        exe = folder / "WITS-Deploy"
        exe.write_text("#!/bin/sh\n" + body)
        exe.chmod(0o755)
        return folder

    def launch(self, new_body, grace=25):
        new, old = self.program("new", new_body), self.program("old", f"touch {self.marker}\n")
        app_update.write_pending(old, new, self.root)
        subprocess.run(app_update.restart_command(new, old, delay=0, grace=grace, directory=self.root), timeout=20)

    def test_a_new_version_that_fails_at_once_falls_back_to_the_old_one(self):
        self.launch("exit 1\n")
        self.assertTrue(self.marker.exists())
        self.assertIsNone(app_update.read_pending(self.root))

    def test_a_healthy_new_version_does_not_start_the_old_one(self):
        self.launch("exit 0\n")
        self.assertFalse(self.marker.exists())

    def test_a_failure_after_the_grace_period_is_not_rolled_back(self):
        self.launch("exit 1\n", grace=0)
        self.assertFalse(self.marker.exists())


class ConfirmTests(unittest.TestCase):
    def test_confirmation_moves_shortcuts_once_and_clears_the_marker(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            app_update.write_pending(Path("/old"), root, root)
            refresh = MagicMock()
            with patch.object(app_update, "app_directory", return_value=root):
                self.assertEqual(app_update.confirm_started(root, refresh), "/old")
                self.assertIsNone(app_update.confirm_started(root, refresh))
            refresh.assert_called_once()

    def test_a_marker_for_another_install_is_left_alone(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            app_update.write_pending(Path("/old"), Path("/somewhere/else"), root)
            refresh = MagicMock()
            with patch.object(app_update, "app_directory", return_value=root):
                self.assertIsNone(app_update.confirm_started(root, refresh))
            refresh.assert_not_called()
            self.assertIsNotNone(app_update.read_pending(root))


class AvailabilityTests(unittest.TestCase):
    def test_reasons(self):
        newer = SignedRelease("9.0.0", None, {"linux-x86_64": {}})
        with patch.object(app_update, "frozen", return_value=False):
            self.assertIn("packaged Linux", app_update.unavailable_reason(newer))
        with patch.object(app_update, "frozen", return_value=True), patch.object(sys, "platform", "linux"):
            self.assertIn("No verified", app_update.unavailable_reason(None))
            self.assertIn("newest", app_update.unavailable_reason(SignedRelease("0.1.0", None, {"linux-x86_64": {}})))
            with tempfile.TemporaryDirectory() as d:
                install = Path(d) / "WITS-Deploy-x"
                install.mkdir()
                (install / "WITS-Deploy").write_text("")
                with patch.object(app_update, "app_directory", return_value=install):
                    self.assertIsNone(app_update.unavailable_reason(newer))
                    os.chmod(d, 0o500)
                    try:
                        if os.geteuid() != 0:
                            self.assertIn("not writable", app_update.unavailable_reason(newer))
                    finally:
                        os.chmod(d, 0o700)


try:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QMessageBox
    from wits_keyboard.app import MainWindow
    QT = True
except ImportError:
    QT = False


@unittest.skipUnless(QT, "Qt not installed")
class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_button_follows_availability_and_busy_boards_block_the_update(self):
        with tempfile.TemporaryDirectory() as d:
            settings = QSettings(str(Path(d) / "s.ini"), QSettings.Format.IniFormat)
            with patch("wits_keyboard.app.AsyncRunner"), patch("wits_keyboard.app.QSettings", return_value=settings):
                window = MainWindow()
            release = SignedRelease("0.2.0-dev20", None, {"linux-x86_64": {}})
            window.signed_app = release
            with patch.object(app_update, "unavailable_reason", return_value="nope"):
                window._offer_app_update()
            self.assertTrue(window.app_update_button.isHidden())
            with patch.object(app_update, "unavailable_reason", return_value=None):
                window._offer_app_update()
                self.assertFalse(window.app_update_button.isHidden())
                self.assertIn("0.2.0-dev20", window.app_update_button.text())
                from wits_keyboard.controller import DiscoveredBoard
                window._add_or_update_device(DiscoveredBoard("A", "Board A"))
                window.states["A"] = {"connected": True, "authenticated": True, "armed": True, "typing": False}
                with patch.object(QMessageBox, "information") as info, \
                        patch("wits_keyboard.app_update_dialog.AppUpdateDialog") as dialog:
                    window._update_app()
                info.assert_called_once()
                dialog.assert_not_called()
            window.close()


if __name__ == "__main__":
    unittest.main()
