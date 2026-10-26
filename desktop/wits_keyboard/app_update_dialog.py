"""Download, verify and install the newest signed app build, then restart into it."""
import threading
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout
from . import __version__, app_update
from .logging_config import safe_error


class AppUpdateDialog(QDialog):
    progress = Signal(int, int)
    finished_download = Signal(object, str)  # new install folder or None, message

    def __init__(self, release, parent=None):
        super().__init__(parent)
        self.release = release
        self.cancelled = threading.Event()
        self.busy = False
        self.installed = None
        self.setWindowTitle("Update WITS Deploy")
        self.resize(560, 260)
        layout = QVBoxLayout(self)
        text = QLabel(
            f"Update from {__version__} to {release.version}.\n\n"
            "The new version is downloaded, checked against the signed release manifest and unpacked "
            f"beside this one in {app_update.app_directory().parent}. This copy is not changed and stays "
            "as a fallback; the app then restarts into the new version and reconnects your boards.")
        text.setTextFormat(Qt.TextFormat.PlainText)
        text.setWordWrap(True)
        layout.addWidget(text)
        self.status = QLabel("")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.bar = QProgressBar()
        layout.addWidget(self.bar)
        row = QHBoxLayout()
        self.go = QPushButton("Download and restart")
        self.go.clicked.connect(self._start)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self._cancel_or_close)
        row.addWidget(self.go)
        row.addWidget(self.close_button)
        layout.addLayout(row)
        self.progress.connect(self._progress)
        self.finished_download.connect(self._finished)

    def _start(self):
        self.busy = True
        self.cancelled.clear()
        self.go.setEnabled(False)
        self.close_button.setText("Cancel")
        self.status.setText("Downloading…")

        def work():
            try:
                folder = app_update.download_app(self.release, progress=self.progress.emit, cancelled=self.cancelled)
                self.finished_download.emit(folder, "")
            except InterruptedError:
                self.finished_download.emit(None, "Canceled; nothing was changed.")
            except Exception as error:
                self.finished_download.emit(None, safe_error(error))
        threading.Thread(target=work, name="wits-app-download", daemon=True).start()

    def _progress(self, done, total):
        self.bar.setMaximum(max(total, 1))
        self.bar.setValue(done)
        self.status.setText(f"Downloading… {done >> 20:,} of {total >> 20:,} MiB")

    def _finished(self, folder, message):
        self.busy = False
        self.close_button.setText("Close")
        if folder is None:
            self.go.setEnabled(True)
            self.status.setText("Update failed; nothing was changed. " + message)
            return
        self.installed = folder
        self.status.setText("Verified and installed. Restarting…")
        self.accept()

    def _cancel_or_close(self):
        if self.busy:
            self.cancelled.set()
            self.close_button.setEnabled(False)
        else:
            self.reject()

    def reject(self):
        if not self.busy:
            super().reject()

    def closeEvent(self, event):
        event.ignore() if self.busy else super().closeEvent(event)
