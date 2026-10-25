import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from PySide6.QtCore import QFileInfo
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    from wits_keyboard.file_choice import PlainIcons, start_directory
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


if __name__ == "__main__":
    unittest.main()
