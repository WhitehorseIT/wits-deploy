"""USB install/update UI, available even when no BLE board is connected."""
import logging
from pathlib import Path
from PySide6.QtCore import QProcess, QProcessEnvironment, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout)
from .firmware_update import BOARD_NAMES, load_release
from .runtime import app_directory, worker_command
from .firmware_bundle import bundled_manifest
from .file_choice import choose_manifest

logger = logging.getLogger(__name__)


class UsbFlashDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("USB Flash/Update")
        self.resize(760, 580)
        self.manifest = None
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._output)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        layout = QVBoxLayout(self)
        hint = QLabel("Safely eject writable storage and cancel any OTA transfer first. Close serial consoles, "
                      "connect the board's programming USB port, and enter FLASH/bootloader mode. "
                      "The 7-inch board uses UART; the 1.47-inch board uses its single USB-C port. "
                      "Blank boards do not need Bluetooth pairing.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.model = QComboBox()
        self.model.addItem("Select the physical board model…", None)
        for key, name in BOARD_NAMES.items(): self.model.addItem(name, key)
        layout.addWidget(self.model)
        row = QHBoxLayout()
        self.port = QComboBox()
        self.port.setEditable(True)
        row.addWidget(self.port, 1)
        refresh = QPushButton("Refresh USB ports")
        refresh.clicked.connect(self._ports)
        row.addWidget(refresh)
        layout.addLayout(row)
        self.refresh = refresh
        self.mode = QComboBox()
        self.mode.addItem("Update working board — preserve pairings", False)
        self.mode.addItem("Install blank board / factory recovery — clear pairings", True)
        layout.addWidget(self.mode)
        self.choose = QPushButton("Choose release .ota.json…")
        self.choose.clicked.connect(self._choose)
        layout.addWidget(self.choose)
        self.description = QLabel("Select the common release manifest and the physical model.")
        self.description.setTextFormat(Qt.TextFormat.PlainText)
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)
        self.bar = QProgressBar()
        layout.addWidget(self.bar)
        row = QHBoxLayout()
        self.flash = QPushButton("USB Flash/Update")
        self.flash.clicked.connect(self._flash)
        row.addWidget(self.flash)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.reject)
        row.addWidget(self.close_button)
        layout.addLayout(row)
        self._ports()
        try:
            path = bundled_manifest()
            if path:
                self._load_manifest(path, included=True)
        except Exception as error:
            self.description.setText("Included firmware unavailable: " + str(error))

    def _ports(self):
        from PySide6.QtSerialPort import QSerialPortInfo
        previous = self.port.currentText()
        self.port.clear()
        for item in QSerialPortInfo.availablePorts():
            self.port.addItem(item.systemLocation())
            self.port.setItemData(self.port.count() - 1, item.description(), Qt.ItemDataRole.ToolTipRole)
        if previous: self.port.setCurrentText(previous)

    def _choose(self):
        path = choose_manifest(self, "Choose release")
        if not path: return
        self._load_manifest(path)

    def _load_manifest(self, path, included=False):
        try:
            release = load_release(path)
            self.manifest = str(Path(path).resolve())
            self.description.setText(f"{'Included firmware' if included else 'Release'} {release.version}: " + ", ".join(BOARD_NAMES[t.board] for t in release.targets))
        except Exception as error:
            self.manifest = None
            self.description.setText(str(error))

    def _busy(self):
        return self.process.state() != QProcess.ProcessState.NotRunning

    def _flash(self):
        if self._busy(): return
        board, port = self.model.currentData(), self.port.currentText().strip()
        if not self.manifest or not board or not port:
            self.description.setText("Choose a release manifest, physical board model and USB port first.")
            return
        if self.mode.currentData():
            answer = QMessageBox.question(self, "Factory installation",
                "Install the factory image? This replaces the flash layout and clears existing board pairings/settings.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes: return
        args = ["--port", port, "--board", board, "--manifest", self.manifest]
        if self.mode.currentData(): args.append("--factory")
        try:
            command = worker_command("usb-flash", *args)
        except RuntimeError as error:
            self.description.setText(str(error))
            return
        self.log.clear()
        self.bar.setRange(0, 0)
        for widget in (self.model, self.port, self.refresh, self.mode, self.choose, self.flash, self.close_button):
            widget.setEnabled(False)
        self.process.setWorkingDirectory(str(app_directory()))
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONIOENCODING", "utf-8")
        environment.insert("PYTHONUNBUFFERED", "1")
        self.process.setProcessEnvironment(environment)
        self.process.start(command[0], command[1:])

    def _output(self):
        self.log.moveCursor(QTextCursor.MoveOperation.End)
        text = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self.log.insertPlainText(text)
        if text.strip(): logger.info("USB flasher: %s", text.strip())
        self.log.ensureCursorVisible()

    def _finished(self, code, _status):
        self._output()
        self.bar.setRange(0, 100)
        success = code == 0 and _status == QProcess.ExitStatus.NormalExit
        self.bar.setValue(100 if success else 0)
        self.description.setText("Firmware verified. Press RESET; the board starts in HID mode." if success else
                                 "USB flash failed. See the output below; keep the board connected for recovery.")
        for widget in (self.model, self.port, self.refresh, self.mode, self.choose, self.flash, self.close_button):
            widget.setEnabled(True)

    def _error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.log.appendPlainText(self.process.errorString())
            self._finished(1, None)

    def reject(self):
        if not self._busy(): super().reject()

    def closeEvent(self, event):
        if self._busy(): event.ignore()
        else: super().closeEvent(event)
