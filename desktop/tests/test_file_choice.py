import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from PySide6.QtCore import QFileInfo, QSettings
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    from wits_keyboard import file_choice
    from wits_keyboard.file_choice import PlainIcons, choose_manifest, start_directory
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False


@unittest.skipUnless(QT_AVAILABLE, "Qt not installed")
class FileChoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_icons_never_depend_on_the_file_existing(self):
        provider = PlainIcons()
        self.assertIsInstance(provider.icon(QFileInfo("/no/such/file.ota.json")), QIcon)
        self.assertIsInstance(provider.icon(QFileInfo("/no/such/folder/")), QIcon)
        self.assertIsInstance(provider.icon(PlainIcons.IconType.File), QIcon)

    def test_picker_starts_in_downloads_when_present(self):
        with patch.object(Path, "home", return_value=Path("/home/someone")), \
                patch.object(Path, "is_dir", return_value=True):
            self.assertEqual(start_directory(), Path("/home/someone/Downloads"))

    def test_picker_falls_back_to_home_without_downloads(self):
        with patch.object(Path, "home", return_value=Path("/home/someone")), \
                patch.object(Path, "is_dir", return_value=False):
            self.assertEqual(start_directory(), Path("/home/someone"))

    def test_picker_reopens_in_the_last_folder_when_it_still_exists(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(start_directory(d), Path(d))

    def test_picker_ignores_a_remembered_folder_that_is_gone(self):
        with patch.object(Path, "home", return_value=Path("/home/someone")):
            self.assertEqual(start_directory("/no/such/folder"), Path("/home/someone"))

    def test_picker_does_not_wait_on_a_remembered_folder_that_hangs(self):
        def hang(self):
            time.sleep(5)
            return True
        with patch.object(Path, "home", return_value=Path("/home/someone")), patch.object(Path, "is_dir", hang):
            started = time.monotonic()
            result = file_choice._responds(Path("/stalled/share"), timeout=0.1)
            self.assertFalse(result)
            self.assertLess(time.monotonic() - started, 1.0)

    def test_choosing_a_file_remembers_its_folder(self):
        with tempfile.TemporaryDirectory() as d:
            settings = QSettings(str(Path(d) / "s.ini"), QSettings.Format.IniFormat)
            chosen = str(Path(d) / "release" / "WITS-Deploy-Release-1.0.0.ota.json")
            with patch.object(file_choice.QFileDialog, "exec", return_value=1), \
                    patch.object(file_choice.QFileDialog, "selectedFiles", return_value=[chosen]):
                self.assertEqual(choose_manifest(None, "Choose", settings), chosen)
            self.assertEqual(settings.value(file_choice.REMEMBERED_KEY), str(Path(chosen).parent))
            with patch.object(file_choice.QFileDialog, "exec", return_value=0):
                self.assertEqual(choose_manifest(None, "Choose", settings), "")
            self.assertEqual(settings.value(file_choice.REMEMBERED_KEY), str(Path(chosen).parent))  # cancel keeps it


if __name__ == "__main__":
    unittest.main()
