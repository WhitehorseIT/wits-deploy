"""File picker that cannot freeze the window on an unreachable network share."""
from pathlib import Path
from PySide6.QtCore import QFileInfo
from PySide6.QtGui import QAbstractFileIconProvider
from PySide6.QtWidgets import QFileDialog


class PlainIcons(QAbstractFileIconProvider):
    """Choose icons by file type only.

    Qt's default provider opens each file to detect its type. When a mounted
    network share stops responding, that read never returns and the whole
    window hangs.
    """

    def icon(self, argument):
        if isinstance(argument, QFileInfo):
            kind = self.IconType.Folder if argument.isDir() else self.IconType.File
            return super().icon(kind)
        return super().icon(argument)


def start_directory():
    # Home often holds mount points for network shares, so start in a local folder.
    downloads = Path.home() / "Downloads"
    return downloads if downloads.is_dir() else Path.home()


def choose_manifest(parent, title):
    """Return the chosen *.ota.json path, or an empty string if cancelled."""
    dialog = QFileDialog(parent, title, str(start_directory()), "WITS OTA manifest (*.ota.json)")
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    dialog.setIconProvider(PlainIcons())
    if dialog.exec() and dialog.selectedFiles():
        return dialog.selectedFiles()[0]
    return ""
