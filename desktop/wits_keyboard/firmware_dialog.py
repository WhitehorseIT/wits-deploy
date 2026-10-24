"""App-managed firmware upload through the selected board's encrypted BLE link."""
import asyncio
import threading
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel,
                              QProgressBar, QPushButton, QVBoxLayout)
from .firmware_update import BOARD_NAMES, load_release
from .logging_config import safe_error


class FirmwareDialog(QDialog):
    progress = Signal(str, int)
    finished_upload = Signal(bool, str)

    def __init__(self, runner, controller, address, name="Selected board", parent=None):
        super().__init__(parent)
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

    def _choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose update manifest", "", "WITS OTA manifest (*.ota.json)")
        if not path:
            return
        try:
            self.image = load_release(path)
            models = ", ".join(BOARD_NAMES[target.board] for target in self.image.targets)
            self.image_label.setText(f"Release {self.image.version} · {models}\n"
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
