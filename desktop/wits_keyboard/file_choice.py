"""File picker that cannot freeze the window on an unreachable network share."""
import threading
from pathlib import Path
from PySide6.QtCore import QFileInfo, QSettings
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


REMEMBERED_KEY = "files/last_manifest_directory"


def _responds(path: Path, timeout: float = 1.0) -> bool:
    """True if ``path`` is a folder and the check came back in time. A stalled network mount can block
    the check forever, so it runs in a helper thread that is simply abandoned if it hangs."""
    answer = []
    worker = threading.Thread(target=lambda: answer.append(path.is_dir()), daemon=True)
    worker.start()
    worker.join(timeout)
    return bool(answer and answer[0])


def start_directory(remembered=None):
    """The folder the picker opens in: the last one used if it is still reachable, else Downloads, else home."""
    if remembered and _responds(Path(str(remembered))):
        return Path(str(remembered))
    # Home often holds mount points for network shares, so fall back to a local folder.
    downloads = Path.home() / "Downloads"
    return downloads if downloads.is_dir() else Path.home()


def choose_manifest(parent, title, settings=None):
    """Return the chosen *.ota.json path, or an empty string if cancelled. Remembers the folder."""
    settings = settings or QSettings("Whitehorse IT Solutions", "WITS Keyboard")
    dialog = QFileDialog(parent, title, str(start_directory(settings.value(REMEMBERED_KEY))),
                         "WITS OTA manifest (*.ota.json)")
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    icons = PlainIcons()  # the dialog does not own its icon provider, so keep it alive for the dialog's lifetime
    dialog.setIconProvider(icons)
    try:
        if dialog.exec() and dialog.selectedFiles():
            chosen = dialog.selectedFiles()[0]
            settings.setValue(REMEMBERED_KEY, str(Path(chosen).parent))
            return chosen
        return ""
    finally:
        dialog.deleteLater()
