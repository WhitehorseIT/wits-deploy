"""App-managed firmware upload through the selected board's encrypted BLE link."""
import asyncio
import threading
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel,
                              QProgressBar, QPushButton, QVBoxLayout)
from .firmware_update import BOARD_NAMES, load_release
from .logging_config import safe_error
from .firmware_bundle import bundled_manifest
from .file_choice import choose_manifest


class FirmwareDialog(QDialog):
    progress = Signal(str, int)
    finished_upload = Signal(bool, str)
    downloaded = Signal(object, str)  # manifest path or None, message

    def __init__(self, runner, controller, address, name="Selected board", parent=None, signed_release=None):
        super().__init__(parent)
        self.signed_release = signed_release
        self.runner = runner
        self.controller = controller
        self.address = address
        self.cancelled = threading.Event()
        self.busy = False
        self.image = None
        self.setWindowTitle("OTA Update")
        self.resize(620, 380)
        layout = QVBoxLayout(self)
        instructions = QLabel(
            f"Update {name} over its existing paired Bluetooth connection. "
            "Disarm and safely eject writable USB storage first. Your internet connection stays unchanged. "
            "Keep power connected; the board display pauses while firmware is written."
        )
        instructions.setTextFormat(Qt.TextFormat.PlainText)
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        self.download = QPushButton("Download latest firmware")
        self.download.clicked.connect(self._download)
        if self.signed_release is not None and "firmware" in self.signed_release.assets:
            self.download.setText(f"Download latest firmware ({self.signed_release.version}, signature verified)")
            layout.addWidget(self.download)
        else:
            self.download.hide()
        self.choose = QPushButton("Choose firmware .ota.json manifest…")
        self.choose.clicked.connect(self._choose)
        layout.addWidget(self.choose)
        self.image_label = QLabel("Select the release manifest; the connected board determines which image is used.")
        self.image_label.setTextFormat(Qt.TextFormat.PlainText)
        self.image_label.setWordWrap(True)
        layout.addWidget(self.image_label)
        self.status = QLabel("The board must already have Bluetooth OTA-capable firmware installed.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.bar = QProgressBar()
        layout.addWidget(self.bar)
        row = QHBoxLayout()
        self.upload = QPushButton("Upload and restart")
        self.upload.setEnabled(False)
        self.upload.clicked.connect(self._upload)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self._cancel_or_close)
        row.addWidget(self.upload)
        row.addWidget(self.close_button)
        layout.addLayout(row)
        self.progress.connect(self._progress)
        self.finished_upload.connect(self._finished)
        self.downloaded.connect(self._downloaded)
        try:
            path = bundled_manifest()
            if path:
                self._load_manifest(path, included=True)
        except Exception as error:
            self.status.setText("Included firmware unavailable: " + safe_error(error))

    def _choose(self):
        path = choose_manifest(self, "Choose update manifest")
        if not path:
            return
        self._load_manifest(path)

    def _download(self):
        from . import online_release
        release = self.signed_release
        self.download.setEnabled(False)
        self.status.setText(f"Downloading firmware {release.version}…")

        def work():
            try:
                path = online_release.download_firmware(
                    release, progress=lambda done, total: self.progress.emit(
                        f"Downloading firmware {release.version}… {done // 1024:,} of {total // 1024:,} KiB", 0))
                self.downloaded.emit(path, "")
            except Exception as error:
                self.downloaded.emit(None, safe_error(error))
        threading.Thread(target=work, name="wits-firmware-download", daemon=True).start()

    def _downloaded(self, path, message):
        self.download.setEnabled(True)
        if path is None:
            self.status.setText("Download failed; nothing was changed. " + message)
            return
        self._load_manifest(path, source="Verified download")
        self.status.setText("Download verified against the signed release manifest.")

    def _load_manifest(self, path, included=False, source=None):
        try:
            self.image = load_release(path)
            models = ", ".join(BOARD_NAMES[target.board] for target in self.image.targets)
            self.image_label.setText(f"{source or ('Included firmware' if included else 'Release')} {self.image.version} · {models}\n"
                                     "The app will select and verify this board's matching binary before uploading.")
            self.upload.setEnabled(True)
        except Exception as error:
            self.image = None
            self.upload.setEnabled(False)
            self.status.setText(safe_error(error))

    def _upload(self):
        if self.busy or self.image is None:
            return
        self.busy = True
        self.cancelled.clear()
        self.choose.setEnabled(False)
        self.upload.setEnabled(False)
        self.close_button.setText("Cancel update")
        async def work():
            try:
                await self.controller.update_firmware(self.address, self.image, self.progress.emit, self.cancelled)
                return True, "Update verified."
            except asyncio.CancelledError:
                return False, "Canceled; the board retains its existing firmware."
        self.runner.submit(work(), on_success=lambda result: self.finished_upload.emit(*result),
            on_error=lambda error: self.finished_upload.emit(False, safe_error(error)), operation="firmware upload")

    def _cancel_or_close(self):
        if self.busy:
            self.cancelled.set()
            self.status.setText("Canceling firmware update…")
            self.close_button.setEnabled(False)
        else:
            self.reject()

    def _progress(self, message, value):
        self.status.setText(message)
        self.bar.setValue(value)
        if value >= 99:
            self.close_button.setEnabled(False)

    def _finished(self, success, message):
        self.busy = False
        self.close_button.setText("Close")
        for widget in (self.choose, self.close_button):
            widget.setEnabled(True)
        self.upload.setEnabled(self.image is not None)
        if not success:
            self.status.setText("Update failed: " + message)

    def reject(self):
        if not self.busy:
            super().reject()

    def closeEvent(self, event):
        if self.busy:
            event.ignore()
        else:
            super().closeEvent(event)
