"""PySide6 desktop interface for one or more WITS Deploy boards."""

from __future__ import annotations

import asyncio
import logging
import json
import sys
import threading
import uuid
import time
import math
from concurrent.futures import CancelledError as FutureCancelledError
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QEventLoop, QObject, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__, protocol
from .controller import DiscoveredBoard, KeyboardController
from . import app_update, online_release, release_check
from .storage_stats import summarize as summarize_storage_io
from .logging_config import LOG_PATH, safe_error

logger = logging.getLogger(__name__)

ADDRESS_ROLE = Qt.ItemDataRole.UserRole


@dataclass(repr=False)
class PasskeyRequest:
    request_id: str
    address: str
    name: str
    loop: asyncio.AbstractEventLoop = field(repr=False)
    future: asyncio.Future[int | None] = field(repr=False)

    def respond(self, value: int | None) -> None:
        def finish() -> None:
            if not self.future.done():
                self.future.set_result(value)

        self.loop.call_soon_threadsafe(finish)


@dataclass(repr=False)
class PendingDelivery:
    addresses: tuple[str, ...]
    label: str
    deadline: float
    deliver: Callable[[], None]


SHUTDOWN_TIMEOUT_S = 3  # most time the app waits for boards to release their Bluetooth links on exit


class ClosingNotice(QDialog):
    """Explains the short wait on exit: boards are disconnected cleanly so they accept a new connection at once."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.remaining_ms = SHUTDOWN_TIMEOUT_S * 1000
        layout = QVBoxLayout(self)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(100)
        self._tick(first=True)

    def _tick(self, first: bool = False) -> None:
        if not first:
            self.remaining_ms = max(self.remaining_ms - 100, 0)
        seconds = (self.remaining_ms + 999) // 1000
        self.label.setText(
            "Disconnecting your boards before closing\n"
            f"Closing in up to {seconds} second{'s' if seconds != 1 else ''}\n\n"
            "This short wait is intentional: it lets each board release its Bluetooth link cleanly.")


class UiBridge(QObject):
    scan_finished = Signal(object)
    task_failed = Signal(str)
    board_event = Signal(str, str, object)
    operation_error = Signal(str, str)
    passkey_requested = Signal(object)
    passkey_finished = Signal(str)
    management_finished = Signal(str, str)
    latest_release = Signal(object)  # (newest tag, signed release or None), or None when the check failed
    shutdown_done = Signal()  # boards released; the window may close
    board_removed = Signal(str, str, str)  # address, name, note about the OS pairing
    update_aborted = Signal()  # the update could not start; restore Auto-connect
    update_ready = Signal(str)  # other boards disconnected; open the updater for this address


class AsyncRunner:
    def __init__(self, bridge: UiBridge) -> None:
        self.bridge = bridge
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(
            target=self._run, name="wits-ble-event-loop", daemon=True
        )
        self.thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.set_debug(True)

        def exception_handler(_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
            exception = context.get("exception")
            logger.error(
                "Async event-loop exception: %s",
                context.get("message", "unknown error"),
                exc_info=(
                    type(exception),
                    exception,
                    exception.__traceback__,
                ) if exception is not None else None,
            )

        self.loop.set_exception_handler(exception_handler)
        logger.debug("BLE asyncio event loop started")
        self.loop.run_forever()
        logger.debug("BLE asyncio event loop stopped")

    def submit(
        self,
        coroutine: Coroutine[Any, Any, Any],
        on_success: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        *,
        operation: str = "background task",
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        logger.debug("Submitting async operation=%s", operation)
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)

        def finished(result_future: Any) -> None:
            try:
                result = result_future.result()
            except FutureCancelledError:
                logger.info("Async operation canceled operation=%s", operation)
                return
            except Exception as error:
                logger.error(
                    "Async operation failed operation=%s error=%s",
                    operation,
                    safe_error(error),
                    exc_info=(type(error), error, error.__traceback__),
                )
                if on_error is not None:
                    on_error(error)
                else:
                    self.bridge.task_failed.emit(str(error))
            else:
                logger.debug("Async operation completed operation=%s", operation)
                if on_success is not None:
                    on_success(result)
            finally:
                if on_finished is not None:
                    on_finished()

        future.add_done_callback(finished)

    def close(self, controller: KeyboardController) -> None:
        if not self.loop.is_running():
            return
        future = asyncio.run_coroutine_threadsafe(controller.disconnect_all(), self.loop)
        try:
            future.result(timeout=SHUTDOWN_TIMEOUT_S)
        except Exception as error:
            logger.warning("Shutdown disconnect failed error=%s", safe_error(error))
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=3)
        logger.info("Async runner closed")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"WITS Deploy {__version__}")
        self.resize(1180, 940)

        self.bridge = UiBridge()
        self.controller = KeyboardController(
            self.bridge.board_event.emit, pairing_callback=self._request_passkey
        )
        self.runner = AsyncRunner(self.bridge)
        # The settings identity keeps its original name on purpose: renaming it would
        # orphan every user's saved boards, names and delays.
        self.settings = QSettings("Whitehorse IT Solutions", "WITS Keyboard")
        self.items: dict[str, QTreeWidgetItem] = {}
        self.states: dict[str, dict[str, Any]] = {}
        self.board_information: dict[str, dict[str, Any]] = {}
        self.storage_io_summary: dict[str, str] = {}
        self.passkey_dialogs: dict[str, QDialog] = {}
        self.management_pending: dict[str, tuple[str, str, float]] = {}
        self.auto_connect_preferences: set[str] = set()
        self.latest_firmware = release_check.bundled_latest()
        self.closing_notice_shown = False
        self.signed_app = None       # newest app release whose signature verified; enables app updates
        self.signed_firmware = None  # newest firmware release whose signature verified; enables online firmware
        self._auto_connect_restore: set[str] = set()  # boards whose Auto-connect is off only during an update
        self.auto_management_tokens: dict[str, str] = {}
        self.auto_status: dict[str, str] = {}
        self.pending_delivery: PendingDelivery | None = None
        self.key_buttons: list[QPushButton] = []
        logger.info("Main window initializing")

        self._build_ui()
        self.bridge.scan_finished.connect(self._scan_finished)
        self.bridge.task_failed.connect(self._task_failed)
        self.bridge.board_event.connect(self._board_event)
        self.bridge.operation_error.connect(self._operation_error)
        self.bridge.update_ready.connect(self._open_firmware_dialog)
        self.bridge.update_aborted.connect(self._restore_auto_connect)
        self.bridge.board_removed.connect(self._board_removed)
        self.bridge.latest_release.connect(self._latest_release_known)
        self.bridge.passkey_requested.connect(self._show_passkey_prompt)
        self.bridge.passkey_finished.connect(self._dismiss_passkey_prompt)
        self.bridge.management_finished.connect(self._management_finished)
        self.connection_timer = QTimer(self)
        self.connection_timer.setInterval(1000)
        self.connection_timer.timeout.connect(self._connection_progress)
        self.connection_timer.start()
        self.delivery_timer = QTimer(self)
        self.delivery_timer.setInterval(100)
        self.delivery_timer.timeout.connect(self._delivery_tick)
        self._restore_devices()
        for address in self.auto_connect_preferences:
            self.runner.submit(self.controller.set_auto_connect(address, True), operation="restore auto-connect")
        self._update_management_buttons()

    def _restore_devices(self) -> None:
        try:
            saved = json.loads(str(self.settings.value("known_devices", "[]")))
            if not isinstance(saved, list):
                raise ValueError("invalid saved device list")
        except (ValueError, TypeError):
            logger.warning("Saved device list is invalid; rediscover boards with Scan")
            saved = []
        # Older versions retained aliases but not their device list.
        self.settings.beginGroup("aliases")
        aliases = list(self.settings.childKeys())
        self.settings.endGroup()
        present = {item["address"] for item in saved
                   if isinstance(item, dict) and isinstance(item.get("address"), str)}
        saved.extend({"address": address, "name": "WITS Deploy"}
                     for address in aliases if address not in present)
        for item in saved:
            if not isinstance(item, dict):
                continue
            address, name = item.get("address"), item.get("name")
            if not isinstance(address, str) or not address or not isinstance(name, str):
                continue
            board = DiscoveredBoard(address, name)
            if item.get("auto_connect") is True:
                self.auto_connect_preferences.add(address)
            self.controller.known_devices[address] = board
            self._add_or_update_device(board)
            self._set_board_status(address, "Saved")
        if self.items:
            self.status_label.setText(f"Restored {len(self.items)} saved device(s). Auto-connect watches enabled rows; Connect pairs manually.")

    def _save_devices(self) -> None:
        self.settings.setValue("known_devices", json.dumps([
            {"address": board.address, "name": board.name, "auto_connect": board.address in self.auto_connect_preferences}
            for board in tuple(self.controller.known_devices.values())
        ]))
        self.settings.sync()

    async def _request_passkey(self, address: str, name: str) -> int | None:
        loop = asyncio.get_running_loop()
        request = PasskeyRequest(uuid.uuid4().hex, address, name, loop, loop.create_future())
        self.bridge.passkey_requested.emit(request)
        try:
            return await request.future
        finally:
            self.bridge.passkey_finished.emit(request.request_id)

    def _show_passkey_prompt(self, request: PasskeyRequest) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Pair WITS Deploy board")
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QVBoxLayout(dialog)
        alias = self.items.get(request.address)
        name = alias.text(1) if alias is not None else request.name
        label = QLabel(f"Enter the six-digit PIN shown on {name}.\n{request.address}")
        label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(label)
        entry = QLineEdit()
        entry.setMaxLength(6)
        entry.setPlaceholderText("Six-digit PIN")
        layout.addWidget(entry)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        submit = buttons.button(QDialogButtonBox.StandardButton.Ok)
        submit.setEnabled(False)
        entry.textChanged.connect(
            lambda text: submit.setEnabled(len(text) == 6 and text.isascii() and text.isdigit())
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        def finished(result: int) -> None:
            text = entry.text()
            valid = len(text) == 6 and text.isascii() and text.isdigit()
            value = int(text) if result == QDialog.DialogCode.Accepted and valid else None
            entry.clear()
            request.respond(value)
            self.passkey_dialogs.pop(request.request_id, None)

        dialog.finished.connect(finished)
        self.passkey_dialogs[request.request_id] = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        entry.setFocus()
        self.status_label.setText(f"Enter the PIN displayed on {name}")

    def _dismiss_passkey_prompt(self, request_id: str) -> None:
        dialog = self.passkey_dialogs.pop(request_id, None)
        if dialog is not None:
            dialog.reject()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)

        heading = QLabel(f"WITS Deploy Controller {__version__}")
        heading.setStyleSheet("font-size: 22px; font-weight: 700;")
        root_layout.addWidget(heading)

        explanation = QLabel(
            "Check explicit targets before sending. Each selected board must also be "
            "physically armed. Submitted text is never written to the event log."
        )
        explanation.setWordWrap(True)
        root_layout.addWidget(explanation)

        diagnostic = QLabel(f"Debug log: {LOG_PATH}")
        diagnostic.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        diagnostic.setStyleSheet("color: #68727d;")
        root_layout.addWidget(diagnostic)

        # Boards across the top give the list the full window width; the sending
        # controls sit below and scroll if the window is short.
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter = splitter
        splitter.setChildrenCollapsible(False)
        root_layout.addWidget(splitter, 1)
        splitter.addWidget(self._build_devices_panel())
        actions = QScrollArea()
        actions.setWidgetResizable(True)
        actions.setFrameShape(QScrollArea.Shape.NoFrame)
        actions.setWidget(self._build_actions_panel())
        splitter.addWidget(actions)
        splitter.setSizes(self._saved_splitter_sizes())
        splitter.splitterMoved.connect(self._save_splitter_sizes)

        bottom = QHBoxLayout()
        self.status_label = QLabel("Ready to scan")
        bottom.addWidget(self.status_label, 1)
        stop_all = QPushButton("STOP ALL")
        stop_all.setStyleSheet(
            "QPushButton { background: #a71927; color: white; font-weight: 700; "
            "padding: 9px 24px; }"
        )
        stop_all.clicked.connect(self._stop_all)
        bottom.addWidget(stop_all)
        root_layout.addLayout(bottom)

    def _build_devices_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumHeight(290)
        layout = QVBoxLayout(panel)

        title = QLabel("Devices")
        title.setStyleSheet("font-size: 17px; font-weight: 700;")
        title_row = QHBoxLayout()
        title_row.addWidget(title)
        title_row.addStretch(1)
        self.app_update_button = QPushButton("Update app…")
        self.app_update_button.setToolTip("A newer, signed version of WITS Deploy is available")
        self.app_update_button.clicked.connect(self._update_app)
        self.app_update_button.hide()
        title_row.addWidget(self.app_update_button)
        layout.addLayout(title_row)

        self.device_tree = QTreeWidget()
        self.device_tree.setHeaderLabels(("Target", "Device", "Board state", "Last result", "Auto-connect", "Firmware"))
        self.device_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.device_tree.setRootIsDecorated(False)
        self.device_tree.setAlternatingRowColors(True)
        self.device_tree.setColumnWidth(1, 185)
        self.device_tree.setColumnWidth(2, 145)
        # Keep both checkbox columns visible in a narrow window: show Auto-connect
        # beside Target, size those two to their contents, and let the last
        # visible column (Last result) absorb or clip the leftover space.
        header = self.device_tree.header()
        header.moveSection(4, 1)
        header.moveSection(5, 4)  # Firmware sits between Board state and Last result
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)  # user-resizable
        self.device_tree.setColumnWidth(5, 120)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        self.device_tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.device_tree.itemChanged.connect(self._device_option_changed)
        self.device_tree.itemSelectionChanged.connect(self._update_management_buttons)
        self.device_tree.setMinimumHeight(130)
        layout.addWidget(self.device_tree, 1)

        row = QHBoxLayout()
        self.scan_button = QPushButton("Scan")
        self.scan_button.clicked.connect(self._scan)
        row.addWidget(self.scan_button)
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self._connect_selected)
        row.addWidget(self.connect_button)
        self.repair_button = QPushButton("Re-pair")
        self.repair_button.setToolTip("Forget the selected board's OS bond and pair again")
        self.repair_button.clicked.connect(self._repair_selected)
        row.addWidget(self.repair_button)
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self._disconnect_selected)
        row.addWidget(self.disconnect_button)
        row.addSpacing(24)
        ping = QPushButton("Ping")
        ping.clicked.connect(self._ping_selected)
        row.addWidget(ping)
        identify = QPushButton("Identify")
        identify.clicked.connect(self._identify_selected)
        row.addWidget(identify)
        rename = QPushButton("Rename")
        rename.clicked.connect(self._rename_selected)
        row.addWidget(rename)
        self.remove_button = QPushButton("Remove")
        self.remove_button.setToolTip("Forget the selected board: remove it from this list and remove its "
                                      "pairing from this computer (including Windows' Bluetooth list)")
        self.remove_button.clicked.connect(self._remove_selected)
        row.addWidget(self.remove_button)
        update = QPushButton("OTA Update…")
        update.clicked.connect(self._update_firmware)
        row.addWidget(update)
        usb_flash = QPushButton("USB Flash/Update…")
        usb_flash.clicked.connect(self._flash_usb)
        row.addWidget(usb_flash)
        row.addSpacing(24)
        self.ping_status_label = QLabel("Ping: not run")
        self.ping_status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.ping_status_label.setStyleSheet("font-weight: 600;")
        row.addWidget(self.ping_status_label, 1)
        layout.addLayout(row)

        storage_row = QHBoxLayout()
        self.storage_refresh_button = QPushButton("Storage status")
        self.storage_refresh_button.clicked.connect(lambda: self._storage_selected(None))
        storage_row.addWidget(self.storage_refresh_button)
        self.storage_readonly_button = QPushButton("Mount read-only")
        self.storage_readonly_button.clicked.connect(lambda: self._storage_selected(False))
        storage_row.addWidget(self.storage_readonly_button)
        self.storage_writable_button = QPushButton("Mount read/write")
        self.storage_writable_button.clicked.connect(lambda: self._storage_selected(True))
        storage_row.addWidget(self.storage_writable_button)
        storage_row.addSpacing(24)
        self.storage_status_label = QLabel("Storage: highlight one connected board")
        self.storage_status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.storage_status_label.setWordWrap(True)
        storage_row.addWidget(self.storage_status_label, 1)
        layout.addLayout(storage_row)

        note = QLabel(
            "Highlight rows for Connect/Disconnect/Ping/Identify; the Target checkboxes "
            "independently control where text and keys are sent. Disarm before changing SD "
            "access. Read-only to read/write works straight away; to go back to read-only, "
            "safely eject the USB drive on the target computer, then refresh Storage status."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #68727d;")
        layout.addWidget(note)
        return panel

    def _build_actions_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self.target_label = QLabel("Targets: none")
        self.target_label.setTextFormat(Qt.TextFormat.PlainText)
        self.target_label.setStyleSheet(
            "font-size: 16px; font-weight: 700; padding: 8px; "
            "background-color: palette(alternate-base); color: palette(text); "
            "border: 1px solid palette(mid); border-radius: 5px;"
        )
        self.target_label.setWordWrap(True)
        layout.addWidget(self.target_label)

        delays = QHBoxLayout()
        delays.addWidget(QLabel("Before sending:"))
        self.start_delay = QDoubleSpinBox()
        self.start_delay.setRange(0, 60)
        self.start_delay.setDecimals(1)
        self.start_delay.setSingleStep(0.5)
        self.start_delay.setSuffix(" s")
        self.start_delay.setValue(self.settings.value("sending/start_delay_s", 0.0, type=float))
        self.start_delay.setToolTip("Countdown before text or special keys are sent; 0 sends immediately.")
        delays.addWidget(self.start_delay)
        delays.addWidget(QLabel("Between characters:"))
        self.character_delay = QSpinBox()
        self.character_delay.setRange(0, protocol.MAX_KEY_INTERVAL_MS)
        self.character_delay.setSingleStep(5)
        self.character_delay.setSuffix(" ms")
        self.character_delay.setValue(self.settings.value(
            "sending/character_delay_ms", protocol.DEFAULT_KEY_INTERVAL_MS, type=int
        ))
        self.character_delay.setToolTip(
            "Text pacing on the board. 0 is fastest; default 25 ms. "
            "Changing this requires firmware 0.1.0 or newer."
        )
        delays.addWidget(self.character_delay)
        delays.addStretch(1)
        layout.addLayout(delays)
        self.start_delay.valueChanged.connect(self._save_delay_settings)
        self.character_delay.valueChanged.connect(self._save_delay_settings)

        countdown = QHBoxLayout()
        self.delivery_status_label = QLabel("No send queued")
        self.delivery_status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.delivery_status_label.setWordWrap(True)
        countdown.addWidget(self.delivery_status_label, 1)
        self.cancel_delivery_button = QPushButton("Cancel delayed send")
        self.cancel_delivery_button.setEnabled(False)
        self.cancel_delivery_button.clicked.connect(lambda: self._cancel_delivery("Canceled by user"))
        countdown.addWidget(self.cancel_delivery_button)
        layout.addLayout(countdown)

        editor_group = QGroupBox("Deployment text")
        editor_layout = QVBoxLayout(editor_group)
        self.text_editor = QPlainTextEdit()
        self.text_editor.setPlaceholderText("Paste a password, product key, or deployment text")
        self.text_editor.textChanged.connect(self._text_changed)
        self.text_editor.setMinimumHeight(90)
        editor_layout.addWidget(self.text_editor, 1)

        options = QHBoxLayout()
        self.mask_text = QCheckBox("Hide text")
        self.mask_text.toggled.connect(self._toggle_mask)
        options.addWidget(self.mask_text)
        self.clear_after = QCheckBox("Clear after sending")
        self.clear_after.setChecked(True)
        options.addWidget(self.clear_after)
        self.length_label = QLabel(f"0 / {protocol.MAX_TEXT_BYTES} bytes")
        options.addStretch(1)
        options.addWidget(self.length_label)
        editor_layout.addLayout(options)

        send_row = QHBoxLayout()
        self.send_button = QPushButton("Send")
        self.send_button.setEnabled(False)
        self.send_button.clicked.connect(self._send_text)
        send_row.addWidget(self.send_button, 1)
        stop_selected = QPushButton("Stop selected")
        stop_selected.clicked.connect(self._stop_selected)
        send_row.addWidget(stop_selected)
        editor_layout.addLayout(send_row)
        # Special keys sit beside the text box, using the width of the wide panel.
        middle = QHBoxLayout()
        middle.addWidget(editor_group, 3)
        layout.addLayout(middle)

        key_group = QGroupBox("Special keys — exactly one target")
        key_layout = QGridLayout(key_group)
        keys = (
            ("Backspace", protocol.KEY_BACKSPACE, 0),
            ("Delete", protocol.KEY_DELETE, 0),
            ("Enter", protocol.KEY_ENTER, 0),
            ("Tab", protocol.KEY_TAB, 0),
            ("Escape", protocol.KEY_ESCAPE, 0),
            ("←", protocol.KEY_LEFT, 0),
            ("→", protocol.KEY_RIGHT, 0),
            ("↑", protocol.KEY_UP, 0),
            ("↓", protocol.KEY_DOWN, 0),
            ("Home", protocol.KEY_HOME, 0),
            ("End", protocol.KEY_END, 0),
            ("Ctrl+A", ord("A"), protocol.MODIFIER_CTRL),
        )
        for index, (label, key_code, modifiers) in enumerate(keys):
            button = QPushButton(label)
            button.clicked.connect(
                lambda _checked=False, code=key_code, mods=modifiers, name=label:
                self._send_key(code, mods, name)
            )
            key_layout.addWidget(button, index // 3, index % 3)
            self.key_buttons.append(button)

        secure_attention = QPushButton("Ctrl+Alt+Delete")
        secure_attention.setStyleSheet("font-weight: 700;")
        secure_attention.clicked.connect(self._secure_attention)
        key_layout.addWidget(secure_attention, 4, 0, 1, 3)
        self.key_buttons.append(secure_attention)
        middle.addWidget(key_group, 2)
        # Match the text box to the special keys' height; spare space goes below.
        editor_group.setMaximumHeight(key_group.sizeHint().height())

        log_group = QGroupBox("Event log — metadata only")
        log_layout = QVBoxLayout(log_group)
        self.event_log = QListWidget()
        self.event_log.setMaximumHeight(64)
        log_layout.addWidget(self.event_log)
        log_buttons = QHBoxLayout()
        copy_log = QPushButton("Copy log")
        copy_log.setToolTip("Copy the events shown above to the clipboard")
        copy_log.clicked.connect(self._copy_log)
        save_logs = QPushButton("Save logs…")
        save_logs.setToolTip("Save the events, the full debug logs and system details in one ZIP file, "
                             "for sending to support")
        save_logs.clicked.connect(self._save_logs)
        clear_log = QPushButton("Clear log")
        clear_log.clicked.connect(self.event_log.clear)
        for button in (copy_log, save_logs, clear_log):
            log_buttons.addWidget(button)
        log_layout.addLayout(log_buttons)
        layout.addWidget(log_group)
        layout.addStretch(1)
        return panel

    def _saved_splitter_sizes(self) -> list[int]:
        try:
            sizes = [int(value) for value in self.settings.value("ui/splitter_sizes", [330, 520])]
            if len(sizes) == 2 and all(value > 0 for value in sizes):
                return sizes
        except (TypeError, ValueError):
            pass
        return [330, 520]

    def _save_splitter_sizes(self, *_args) -> None:
        self.settings.setValue("ui/splitter_sizes", self.main_splitter.sizes())

    def _event_lines(self) -> list[str]:
        """The on-screen events, oldest first (the list itself shows the newest at the top)."""
        return [self.event_log.item(i).text() for i in range(self.event_log.count() - 1, -1, -1)]

    def _copy_log(self) -> None:
        QApplication.clipboard().setText("\n".join(self._event_lines()))
        self.status_label.setText(f"Copied {self.event_log.count()} log lines to the clipboard")

    def _save_logs(self) -> None:
        from . import log_bundle
        from .file_choice import choose_save_path
        path = choose_save_path(self, "Save logs", log_bundle.suggested_name(), settings=self.settings)
        if not path:
            return
        try:
            saved = log_bundle.build_bundle(path, self._event_lines(), LOG_PATH.parent)
        except OSError as error:
            QMessageBox.warning(self, "Could not save logs", f"The logs could not be saved: {error}")
            return
        self._log(f"Saved logs to {saved}")
        self.status_label.setText(f"Saved logs to {saved}")

    def _log(self, message: str) -> None:
        logger.info("Event log: %s", message)  # the on-screen list is short-lived; keep a copy in the log file
        self.event_log.insertItem(0, message)
        while self.event_log.count() > 200:
            self.event_log.takeItem(self.event_log.count() - 1)

    def _scan(self) -> None:
        logger.info("UI scan requested")
        self.scan_button.setEnabled(False)
        self.status_label.setText("Scanning for WITS Deploy boards…")
        self.runner.submit(
            self.controller.scan(),
            self.bridge.scan_finished.emit,
            operation="scan",
        )

    def _scan_finished(self, boards: list[DiscoveredBoard]) -> None:
        logger.info("UI scan finished count=%d", len(boards))
        self.scan_button.setEnabled(True)
        for board in boards:
            self.controller.known_devices[board.address] = board
            self._add_or_update_device(board)
        self._save_devices()
        count = len(boards)
        self.status_label.setText(f"Found {count} WITS Deploy board{'s' if count != 1 else ''}")
        self._log(f"Scan completed: {count} board{'s' if count != 1 else ''} found")

    def _add_or_update_device(self, board: DiscoveredBoard) -> None:
        item = self.items.get(board.address)
        if item is None:
            item = QTreeWidgetItem(self.device_tree)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            item.setData(1, ADDRESS_ROLE, board.address)
            self.items[board.address] = item
        was_blocked = self.device_tree.blockSignals(True)
        item.setCheckState(4, Qt.CheckState.Checked if board.address in self.auto_connect_preferences else Qt.CheckState.Unchecked)
        item.setToolTip(4, "Reconnect this saved paired board automatically. Manual Disconnect pauses until Connect, toggle or app restart.")
        self.device_tree.blockSignals(was_blocked)
        alias = self.settings.value(f"aliases/{board.address}", board.name)
        item.setText(1, str(alias))
        item.setToolTip(1, f"{board.name}\n{board.address}")
        if not item.text(2):
            self._set_board_status(board.address, "Discovered")

    @staticmethod
    def _board_state_label(state: dict[str, Any]) -> str:
        if not state.get("connected"):
            return "Offline"
        if not state.get("authenticated"):
            return "Authenticating"
        if state.get("typing"):
            return "TYPING"
        return "ARMED" if state.get("armed") else "DISARMED"

    def _device_option_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column == 0:
            self._targets_changed()
        elif column == 4:
            address = str(item.data(1, ADDRESS_ROLE) or "")
            if not address:
                return
            enabled = item.checkState(4) == Qt.CheckState.Checked
            if enabled:
                self.auto_connect_preferences.add(address)
            else:
                self.auto_connect_preferences.discard(address)
            self._save_devices()
            self.runner.submit(self.controller.set_auto_connect(address, enabled), operation="configure auto-connect")

    def _set_board_status(self, address: str, label: str) -> None:
        item = self.items[address]
        item.setText(2, label)
        badge = self.device_tree.itemWidget(item, 2)
        if badge is None:
            badge = QLabel()
            badge.setTextFormat(Qt.TextFormat.PlainText)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.device_tree.setItemWidget(item, 2, badge)
        badge.setText(label.upper())
        colors = {
            "DISARMED": ("#145c43", "#ffffff"),
            "ARMED": ("#a71927", "#ffffff"),
            "TYPING": ("#843900", "#ffffff"),
            "AUTHENTICATING": ("#654b00", "#ffffff"),
            "CONNECTING": ("#654b00", "#ffffff"),
            "RE-PAIRING": ("#654b00", "#ffffff"),
        }
        background, foreground = colors.get(label.upper(), ("palette(alternate-base)", "palette(text)"))
        badge.setStyleSheet(
            f"background-color: {background}; color: {foreground}; "
            "font-weight: 700; padding: 4px 6px; border-radius: 4px; "
            "border: 1px solid palette(mid);"
        )
        description = {
            "DISARMED": "Connected and authenticated; physically arm the board to enable typing.",
            "ARMED": "Physically armed; this board can type to its USB target.",
            "TYPING": "The board is currently typing to its USB target.",
            "AUTHENTICATING": "Bluetooth link is up; authentication has not completed.",
            "OFFLINE": "Disconnected; the app cannot verify the board's current physical state.",
        }.get(label.upper(), label)
        badge.setToolTip(description)
        item.setToolTip(2, description)
        item.setSizeHint(2, QSize(0, max(30, badge.sizeHint().height() + 4)))

    def _selected_addresses(self) -> list[str]:
        return [
            str(item.data(1, ADDRESS_ROLE))
            for item in self.device_tree.selectedItems()
        ]

    def _target_addresses(self) -> list[str]:
        return [
            address
            for address, item in self.items.items()
            if item.checkState(0) == Qt.CheckState.Checked
        ]

    def _require_management_selection(self) -> list[str]:
        addresses = self._selected_addresses()
        if not addresses:
            QMessageBox.information(self, "Select a board", "Highlight at least one device row first.")
        return addresses

    def _connect_selected(self) -> None:
        for address in self._require_management_selection():
            if self.states.get(address, {}).get("connected"):
                logger.info("Ignoring UI connect; already connected address=%s", address)
                continue
            if address in self.management_pending:
                logger.info("Ignoring duplicate UI connect address=%s", address)
                self._connection_progress()
                continue
            logger.info("UI connect requested address=%s", address)
            token = self._begin_management(address, "Connecting")
            self._set_board_status(address, "Connecting")
            self.runner.submit(
                self.controller.connect(address),
                on_error=lambda error, target=address:
                self.bridge.operation_error.emit(target, str(error)),
                operation=f"connect {address}",
                on_finished=lambda target=address, current=token:
                self.bridge.management_finished.emit(target, current),
            )

    def _begin_management(self, address: str, action: str) -> str:
        self._cancel_delivery_for([address], "Connection operation started")
        token = uuid.uuid4().hex
        self.management_pending[address] = (token, action, time.monotonic())
        self._log(f"{action}: {self.items[address].text(1)}")
        self._connection_progress()
        self._update_management_buttons()
        return token

    def _management_finished(self, address: str, token: str) -> None:
        pending = self.management_pending.get(address)
        if pending is None or pending[0] != token:
            return  # A canceled connect may finish after Re-pair has begun.
        self.management_pending.pop(address, None)
        state = self.states.get(address, {})
        item = self.items[address]
        if item.text(2) in {"Connecting", "Re-pairing"}:
            self._set_board_status(address, self._board_state_label(state))
        self.status_label.setText(
            f"Connected to {item.text(1)}" if state.get("authenticated") else
            f"Connection ended for {item.text(1)} — see Last result"
        )
        self._update_management_buttons()

    def _connection_progress(self) -> None:
        addresses = self._selected_addresses()
        address = next((a for a in addresses if a in self.management_pending), None)
        if address is None:
            address = next(iter(self.management_pending), None)
        if address is None or self.passkey_dialogs:
            return
        _, action, started = self.management_pending[address]
        seconds = int(time.monotonic() - started)
        self.status_label.setText(
            f"{action}: {self.items[address].text(1)} ({seconds}s). "
            "Cancel connection stops this attempt."
        )

    def _update_management_buttons(self) -> None:
        addresses = self._selected_addresses()
        pending = any(a in self.management_pending for a in addresses)
        self.connect_button.setText("Connecting…" if pending else "Connect")
        self.connect_button.setEnabled(any(
            a not in self.management_pending and not self.states.get(a, {}).get("connected")
            for a in addresses
        ))
        self.disconnect_button.setText("Cancel connection" if pending else "Disconnect")
        self.disconnect_button.setEnabled(any(
            a in self.management_pending or self.states.get(a, {}).get("connected")
            or self.auto_status.get(a) in {"watching", "waiting", "connecting"}
            for a in addresses
        ))
        self.repair_button.setEnabled(
            len(addresses) == 1 and
            self.management_pending.get(addresses[0], (None, None, None))[1] != "Re-pairing"
        )
        self._update_storage_controls()

    def _update_storage_controls(self) -> None:
        addresses = self._selected_addresses()
        address = addresses[0] if len(addresses) == 1 else None
        state = self.states.get(address, {})
        connected = bool(state.get("connected") and state.get("authenticated"))
        info = self.board_information.get(address, {}) if connected else {}
        self.storage_refresh_button.setEnabled(connected)
        can_change = bool(connected and info.get("supported") and info.get("present")
                          and not info.get("error") and not state.get("armed") and not state.get("typing"))
        exported, writable = bool(info.get("exported")), bool(info.get("writable"))
        # Read-only to read/write works on a live export; every other change needs the
        # drive ejected on the computer first.
        self.storage_readonly_button.setEnabled(can_change and not exported)
        self.storage_writable_button.setEnabled(can_change and (not exported or not writable))
        if not connected:
            message = "Storage: highlight one connected board"
        elif not info:
            message = "Storage status unknown; refresh (requires new firmware)"
        else:
            name = self.items[address].text(1)
            if not info.get("supported"):
                mode = "storage unsupported"
            elif info.get("error"):
                mode = "SD error — reset to retry"
            elif not info.get("present"):
                mode = "SD unavailable — insert card and reset"
            elif not info.get("exported"):
                mode = "ejected — choose access mode to remount"
            else:
                mode = "READ/WRITE" if info.get("writable") else "READ ONLY"
            capacity = f" · {info['bytes'] / (1024 * 1024):,.0f} MiB" if info.get("present") else ""
            message = f"{name} · FW {info.get('firmware', '?')} · {mode}{capacity}"
            if self.storage_io_summary.get(address):
                message += "\n" + self.storage_io_summary[address]
        self.storage_status_label.setText(message)

    def _storage_selected(self, allow_writes: bool | None) -> None:
        addresses = self._require_management_selection()
        if len(addresses) != 1:
            if addresses:
                QMessageBox.information(self, "Select one board", "Highlight exactly one board for storage controls.")
            return
        address = addresses[0]
        if allow_writes is not None:
            self._cancel_delivery_for([address], "Storage access change requested")
        operation = self.controller.read_info(address) if allow_writes is None else \
            self.controller.storage_mode(address, allow_writes)
        self.runner.submit(
            operation,
            on_error=lambda error: self.bridge.operation_error.emit(address, safe_error(error)),
            operation=f"storage {address}",
        )

    def _flash_usb(self) -> None:
        from .usb_flash_dialog import UsbFlashDialog
        self._cancel_delivery("USB flasher opened")
        dialog = UsbFlashDialog(self)
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()

    def _update_firmware(self) -> None:
        addresses = self._require_management_selection()
        if len(addresses) != 1:
            if addresses:
                QMessageBox.information(self, "Select one board", "Highlight exactly one board to update.")
            return
        address = addresses[0]
        state = self.states.get(address, {})
        if not state.get("connected") or not state.get("authenticated") or state.get("armed") or state.get("typing"):
            self._operation_error(address, RuntimeError("Connect and disarm the selected board before updating"))
            return
        connected = [other for other, other_state in self.states.items()
                     if other != address and other_state.get("connected") and other in self.items]
        if connected:
            # Bluetooth shares airtime between connections: with several boards connected an
            # update measured 0.4 KB/s against 12 KB/s with one, so only one board stays connected.
            names = ", ".join(self.items[other].text(1) for other in connected)
            answer = QMessageBox.question(
                self, "Other boards are connected",
                f"{names} {'is' if len(connected) == 1 else 'are'} also connected. A Bluetooth update runs "
                "far slower (often more than 20 times slower) while other boards are connected.\n\n"
                "Disconnect the other board(s) first? Auto-connect is switched off for every board during "
                "the update and restored afterwards.")
            if answer != QMessageBox.StandardButton.Yes:
                return
            self._cancel_delivery_for(connected, "Disconnected for a firmware update")
        # Auto-connect could otherwise (re)connect any ticked board mid-update, connected or not.
        # Untick every ticked box now (the saved setting is restored when the updater closes).
        others = [other for other in self.items if other != address]
        for board in (address, *others):
            if self.items[board].checkState(4) == Qt.CheckState.Checked:
                self._auto_connect_restore.add(board)
                self.items[board].setCheckState(4, Qt.CheckState.Unchecked)
        if not others:
            self._open_firmware_dialog(address)
            return

        def failed(error: Exception) -> None:
            self.bridge.operation_error.emit(address, safe_error(error))
            self.bridge.update_aborted.emit()  # runs off the interface thread

        # Also cancels connection attempts that are still in progress.
        self.runner.submit(
            self.controller.disconnect_many(others),
            on_success=lambda _result: self.bridge.update_ready.emit(address),
            on_error=failed,
            operation="disconnect other boards for update",
        )

    def _open_firmware_dialog(self, address: str) -> None:
        from .firmware_dialog import FirmwareDialog
        if address not in self.items:
            self._restore_auto_connect()
            return
        self._cancel_delivery("Firmware updater opened")
        dialog = FirmwareDialog(self.runner, self.controller, address, self.items[address].text(1), self,
                                signed_release=self.signed_firmware)
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()  # delete it here, on the interface thread, rather than leave it parented
            self._restore_auto_connect()

    FIRMWARE_COLORS = {release_check.CURRENT: "#145c43", release_check.UPDATE: "#8a6500",
                       release_check.CRITICAL: "#a71927"}  # fills, matching the board-state badges
    FIRMWARE_MEANING = {release_check.CURRENT: "up to date", release_check.UPDATE: "an update is available",
                        release_check.CRITICAL: "critical update available"}

    def _show_firmware(self, address: str, version: str) -> None:
        item = self.items[address]
        item.setText(5, version)
        status = release_check.classify(version, self.latest_firmware)
        if status is None:
            item.setData(5, Qt.ItemDataRole.BackgroundRole, None)
            item.setData(5, Qt.ItemDataRole.ForegroundRole, None)
            item.setToolTip(5, "")
            return
        # Highlight the cell; the text stays white.
        item.setBackground(5, QColor(self.FIRMWARE_COLORS[status]))
        item.setForeground(5, QColor("#ffffff"))
        item.setToolTip(5, f"{self.FIRMWARE_MEANING[status].capitalize()} (newest known: {self.latest_firmware.version})")

    def start_release_check(self) -> None:
        """Look for a newer release in the background; silent when offline."""
        def check():
            tags = online_release.fetch_listing()  # one request; the app and firmware are separate release streams
            if tags is None:
                self.bridge.latest_release.emit(None)
                return
            self.bridge.latest_release.emit({
                kind: (release_check.newest_from_tags(tags, prefix),
                       online_release.latest_signed(kind=kind, tags=tags))
                for kind, prefix in online_release.KINDS.items()})
        threading.Thread(target=check, name="wits-release-check", daemon=True).start()

    def _latest_release_known(self, result) -> None:
        """``result`` maps "app" and "firmware" to (newest tag, verified signed release or None)."""
        if result is None:
            self._log("Release check skipped or offline; comparing against the firmware bundled with this app")
            return
        tag, signed = result["firmware"]
        if signed is not None:
            self.signed_firmware = signed
            tag = release_check.Latest(signed.version, signed.critical_below)
        self.latest_firmware = release_check.newest(self.latest_firmware, tag)
        if tag is not None:
            self._log(f"Newest published firmware: {tag.version}"
                      + (" (signature verified)" if signed is not None else " (no verified signature; online download unavailable)"))
        _app_tag, signed_app = result["app"]
        if signed_app is not None:
            self.signed_app = signed_app
        self._offer_app_update()
        for address, item in self.items.items():
            if item.text(5):
                self._show_firmware(address, item.text(5))

    def _offer_app_update(self) -> None:
        reason = app_update.unavailable_reason(self.signed_app)
        self.app_update_button.setVisible(reason is None)
        if reason is None:
            self.app_update_button.setText(f"Update app to {self.signed_app.version}…")
            self._log(f"App update available: {self.signed_app.version}")

    def _update_app(self) -> None:
        from .app_update_dialog import AppUpdateDialog
        busy = [self.items[a].text(1) for a, state in self.states.items()
                if a in self.items and (state.get("armed") or state.get("typing"))]
        if busy:
            QMessageBox.information(self, "Boards are busy",
                                    f"Disarm {', '.join(busy)} before updating the app.")
            return
        release = self.signed_app
        if release is None or app_update.unavailable_reason(release):
            return
        dialog = AppUpdateDialog(release, self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        installed = dialog.installed
        dialog.deleteLater()
        if accepted and installed is not None:
            try:
                app_update.restart(installed)
            except OSError as error:
                self._log(f"Could not restart into the new version: {error}")
                QMessageBox.warning(self, "Restart failed", f"The update is installed in {installed}, "
                                    f"but the app could not restart itself: {error}")
                return
            self.close()

    def _restore_auto_connect(self) -> None:
        restore, self._auto_connect_restore = self._auto_connect_restore, set()
        for address in restore:
            item = self.items.get(address)
            if item is not None:
                item.setCheckState(4, Qt.CheckState.Checked)

    def _repair_selected(self) -> None:
        addresses = self._require_management_selection()
        if len(addresses) != 1:
            if addresses:
                QMessageBox.information(
                    self, "Re-pair", "Highlight exactly one device to re-pair."
                )
            return
        address = addresses[0]
        item = self.items[address]
        answer = QMessageBox.question(
            self,
            "Re-pair device",
            f"First hold the board's left button until its PIN is displayed.\n\n"
            f"Re-pair {item.text(1)}? This removes only this board's saved "
            "Bluetooth bond from this computer, then requests a new PIN.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        token = self._begin_management(address, "Re-pairing")
        self._set_board_status(address, "Re-pairing")
        logger.info("UI repair pairing requested address=%s", address)
        self.runner.submit(
            self.controller.repair(address),
            on_error=lambda error, target=address:
            self.bridge.operation_error.emit(target, str(error)),
            operation=f"repair pairing {address}",
            on_finished=lambda: self.bridge.management_finished.emit(address, token),
        )

    def _disconnect_selected(self) -> None:
        for address in self._require_management_selection():
            self._cancel_delivery_for([address], "Target disconnected")
            logger.info("UI disconnect requested address=%s", address)
            self.runner.submit(
                self.controller.disconnect(address),
                on_error=lambda error, target=address:
                self.bridge.operation_error.emit(target, str(error)),
                operation=f"disconnect {address}",
            )

    def _ping_selected(self) -> None:
        for address in self._require_management_selection():
            logger.info("UI ping requested address=%s", address)
            item = self.items[address]
            message = f"{item.text(1)}: Ping sent; awaiting reply…"
            self.ping_status_label.setText(message)
            self.status_label.setText(message)
            item.setText(3, "Ping sent; awaiting reply…")
            item.setToolTip(3, message)
            self._log(message)
            self.runner.submit(
                self.controller.ping(address),
                on_error=lambda error, target=address:
                self.bridge.board_event.emit(target, "ping_failed", {"message": safe_error(error)}),
                operation=f"ping {address}",
            )

    def _identify_selected(self) -> None:
        for address in self._require_management_selection():
            state = self.states.get(address, {})
            if state.get("armed"):
                self._operation_error(address, RuntimeError("disarm before identifying"))
                continue
            self.runner.submit(
                self.controller.identify(address, self.items[address].text(1)),
                on_error=lambda error, target=address:
                self.bridge.operation_error.emit(target, str(error)),
                operation=f"identify {address}",
            )

    def _remove_selected(self) -> None:
        addresses = self._require_management_selection()
        if not addresses:
            return
        names = ", ".join(self.items[a].text(1) for a in addresses)
        answer = QMessageBox.question(
            self, "Remove board",
            f"Remove {names} from WITS Deploy?\n\nThis disconnects it, removes it from this list and "
            "removes its pairing from this computer (on Windows, from the Bluetooth devices list too). "
            "The board itself is not changed. To use it again, open its pairing window and Scan.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        for address in addresses:
            self._cancel_delivery_for([address], "Board removed")
            logger.info("UI remove requested address=%s", address)
            name = self.items[address].text(1)
            self.runner.submit(
                self.controller.remove(address),
                on_success=lambda note, target=address, label=name: self.bridge.board_removed.emit(target, label, note),
                on_error=lambda error, target=address, label=name: self.bridge.board_removed.emit(
                    target, label, "Could not finish removing it: " + safe_error(error)),
                operation=f"remove {address}",
            )

    def _board_removed(self, address: str, name: str, note: str) -> None:
        item = self.items.pop(address, None)
        if item is not None:
            self.device_tree.takeTopLevelItem(self.device_tree.indexOfTopLevelItem(item))
        for table in (self.states, self.board_information, self.storage_io_summary, self.management_pending,
                      self.auto_status, self.auto_management_tokens):
            table.pop(address, None)
        self.auto_connect_preferences.discard(address)
        self.settings.remove(f"aliases/{address}")
        self._save_devices()
        self._targets_changed()
        self._update_management_buttons()
        self._log(f"Removed {name}. {note}")
        self.status_label.setText(f"Removed {name}")

    def _rename_selected(self) -> None:
        addresses = self._require_management_selection()
        if len(addresses) != 1:
            if addresses:
                QMessageBox.information(self, "Rename", "Highlight exactly one device.")
            return
        address = addresses[0]
        item = self.items[address]
        alias, accepted = QInputDialog.getText(self, "Device alias", "Friendly name:", text=item.text(1))
        alias = alias.strip()
        if accepted and alias:
            self.settings.setValue(f"aliases/{address}", alias)
            self.settings.sync()
            item.setText(1, alias)
            self._targets_changed()

    def _targets_changed(self, *_args: Any) -> None:
        addresses = self._target_addresses()
        names = [self.items[address].text(1) for address in addresses]
        self.target_label.setText("Targets: " + (", ".join(names) if names else "none"))
        count = len(addresses)
        self.send_button.setText(
            "Send" if count == 0 else f"Send to {names[0]}" if count == 1 else f"Send to {count} devices"
        )
        self._update_send_enabled()

    def _text_changed(self) -> None:
        length = len(self.text_editor.toPlainText().encode("utf-8"))
        self.length_label.setText(f"{length} / {protocol.MAX_TEXT_BYTES} bytes")
        self.length_label.setStyleSheet("color: #a71927;" if length > protocol.MAX_TEXT_BYTES else "")
        self._update_send_enabled()

    def _toggle_mask(self, hidden: bool) -> None:
        if hidden:
            self.text_editor.setStyleSheet(
                "QPlainTextEdit { color: transparent; selection-color: transparent; }"
            )
        else:
            self.text_editor.setStyleSheet("")

    def _valid_targets(self, *, require_single: bool = False) -> list[str]:
        if self.pending_delivery is not None:
            QMessageBox.information(self, "Send pending", "Wait for the countdown or cancel the delayed send first.")
            return []
        addresses = self._target_addresses()
        if not addresses:
            QMessageBox.information(self, "Choose targets", "Check at least one target device.")
            return []
        if require_single and len(addresses) != 1:
            QMessageBox.warning(self, "One target required", "This action requires exactly one target.")
            return []
        unavailable = []
        for address in addresses:
            state = self.states.get(address, {})
            if not state.get("connected") or not state.get("authenticated"):
                unavailable.append(f"{self.items[address].text(1)} is not connected")
            elif not state.get("armed"):
                unavailable.append(f"{self.items[address].text(1)} is not physically armed")
            elif state.get("typing"):
                unavailable.append(f"{self.items[address].text(1)} is already typing")
        if unavailable:
            QMessageBox.warning(self, "Targets not ready", "\n".join(unavailable))
            return []
        return addresses

    def _update_send_enabled(self) -> None:
        ready = self.pending_delivery is None
        self.send_button.setEnabled(bool(ready and self._target_addresses() and self.text_editor.toPlainText()))
        for button in self.key_buttons:
            button.setEnabled(ready)

    def _save_delay_settings(self, *_args: Any) -> None:
        self.settings.setValue("sending/start_delay_s", self.start_delay.value())
        self.settings.setValue("sending/character_delay_ms", self.character_delay.value())
        self.settings.sync()

    def _queue_delivery(self, addresses: list[str], label: str, deliver: Callable[[], None]) -> None:
        seconds = self.start_delay.value()
        if seconds == 0:
            names = ", ".join(self.items[address].text(1) for address in addresses)
            self.delivery_status_label.setText(f"{label} submitted to {names}")
            deliver()
            return
        self.pending_delivery = PendingDelivery(tuple(addresses), label, time.monotonic() + seconds, deliver)
        self.start_delay.setEnabled(False)
        self.character_delay.setEnabled(False)
        self.cancel_delivery_button.setEnabled(True)
        self._update_send_enabled()
        self.delivery_timer.start()
        self._delivery_tick()
        self._log(f"{label} scheduled in {seconds:g} s for {len(addresses)} target(s); content omitted")

    def _clear_delivery(self) -> PendingDelivery | None:
        pending, self.pending_delivery = self.pending_delivery, None
        self.delivery_timer.stop()
        self.cancel_delivery_button.setEnabled(False)
        self.start_delay.setEnabled(True)
        self.character_delay.setEnabled(True)
        self._update_send_enabled()
        return pending

    def _cancel_delivery(self, reason: str) -> None:
        if self._clear_delivery() is not None:
            message = f"Delayed send canceled: {reason}"
            self.delivery_status_label.setText(message)
            self.status_label.setText(message)
            self._log(message)

    def _cancel_delivery_for(self, addresses: list[str], reason: str) -> None:
        if self.pending_delivery is not None and set(addresses).intersection(self.pending_delivery.addresses):
            self._cancel_delivery(reason)

    def _delivery_tick(self) -> None:
        pending = self.pending_delivery
        if pending is None:
            return
        for address in pending.addresses:
            state = self.states.get(address, {})
            if not (state.get("connected") and state.get("authenticated") and state.get("armed")) \
                    or state.get("typing"):
                self._cancel_delivery("Target is no longer connected, armed and idle")
                return
        remaining = pending.deadline - time.monotonic()
        names = ", ".join(self.items[address].text(1) for address in pending.addresses)
        if remaining > 0:
            self.delivery_status_label.setText(
                f"{pending.label} to {names} in {math.ceil(remaining)} s — focus the target window"
            )
            return
        pending = self._clear_delivery()
        self.delivery_status_label.setText(f"{pending.label} submitted to {names}")
        pending.deliver()

    def _send_text(self) -> None:
        addresses = self._valid_targets()
        if not addresses:
            return
        text = self.text_editor.toPlainText()
        try:
            encoded = protocol.encode_text(text)
            protocol.wipe(encoded)
        except protocol.ProtocolError as error:
            QMessageBox.warning(self, "Invalid text", str(error))
            return

        if len(addresses) > 1:
            names = "\n".join(f"• {self.items[address].text(1)}" for address in addresses)
            answer = QMessageBox.question(
                self,
                "Confirm multi-device send",
                f"Send the same text to these {len(addresses)} physically armed devices?\n\n"
                f"{names}\n\nFailures will not be retried automatically.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        clear_after = self.clear_after.isChecked()
        interval = self.character_delay.value()
        def deliver() -> None:
            if clear_after and self.text_editor.toPlainText() == text:
                self.text_editor.clear()
            self._log(f"Text submission started for {len(addresses)} target(s); content omitted")
            logger.info("UI text send requested targets=%s bytes=%d interval_ms=%d content=omitted",
                        addresses, len(text.encode("ascii")), interval)
            self.runner.submit(self.controller.send_text_many(addresses, text, interval), operation="send text")
        self._queue_delivery(addresses, "Text", deliver)

    def _stop_selected(self) -> None:
        addresses = self._target_addresses()
        self._cancel_delivery_for(addresses, "Stop selected")
        if not addresses:
            QMessageBox.information(self, "Choose targets", "Check at least one target device.")
            return
        self.runner.submit(
            self.controller.stop_many(addresses), operation="stop selected"
        )

    def _stop_all(self) -> None:
        self._cancel_delivery("STOP ALL")
        self.status_label.setText("Sending STOP to every connected board…")
        self.runner.submit(self.controller.stop_all(), operation="stop all")

    def _send_key(self, key_code: int, modifiers: int, label: str) -> None:
        addresses = self._valid_targets(require_single=True)
        if not addresses:
            return
        address = addresses[0]
        def deliver() -> None:
            self._log(f"{label} requested for {self.items[address].text(1)}")
            self.runner.submit(
                self.controller.key_action(address, key_code, modifiers),
                on_error=lambda error: self.bridge.operation_error.emit(address, str(error)),
                operation=f"key action {address}",
            )
        self._queue_delivery(addresses, label, deliver)

    def _secure_attention(self) -> None:
        addresses = self._valid_targets(require_single=True)
        if not addresses:
            return
        address = addresses[0]
        answer = QMessageBox.warning(
            self,
            "Confirm secure attention",
            f"Send Ctrl+Alt+Delete to {self.items[address].text(1)} now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._send_key(
                protocol.KEY_DELETE,
                protocol.MODIFIER_CTRL | protocol.MODIFIER_ALT,
                "Ctrl+Alt+Delete",
            )

    def _board_event(self, address: str, event: str, details: dict[str, Any]) -> None:
        logger.debug("UI board event address=%s event=%s details=%s", address, event, details)
        item = self.items.get(address)
        if item is None:
            return
        if event == "auto_connect":
            status, message = details["status"], details["message"]
            self.auto_status[address] = status
            if status == "connecting" and address not in self.management_pending:
                self.auto_management_tokens[address] = self._begin_management(address, "Auto-connecting")
                self._set_board_status(address, "Connecting")
            elif status != "connecting":
                token = self.auto_management_tokens.pop(address, None)
                if token is not None:
                    self._management_finished(address, token)
                if status == "watching" and not self.states.get(address, {}).get("connected") and address not in self.management_pending:
                    self._set_board_status(address, "Watching")
            item.setText(3, message)
            item.setToolTip(4, message)
            self._log(f"{item.text(1)}: {message}")
            self._update_management_buttons()
            return
        if event == "state":
            self.states[address] = details
            if not details.get("connected"):
                self.board_information.pop(address, None)
                self.storage_io_summary.pop(address, None)
            if not (details.get("connected") and details.get("authenticated") and details.get("armed")) \
                    or details.get("typing"):
                self._cancel_delivery_for([address], "Target disconnected, disarmed or became busy")
            self._set_board_status(address, self._board_state_label(details))
            self._update_send_enabled()
            self._update_management_buttons()
            return
        if event == "board_info":
            previous = self.board_information.get(address, {}).get("io")
            summary = summarize_storage_io(previous, details.get("io"))
            if summary:
                self.storage_io_summary[address] = summary
            self.board_information[address] = details
            if address in self.items:
                self._show_firmware(address, str(details.get("firmware") or ""))
            self._update_storage_controls()
            return
        if event == "ping":
            message = f"Ping acknowledged — {details['milliseconds']} ms"
        elif event == "ping_failed":
            message = f"Ping failed: {details.get('message', 'unknown error')}"
        else:
            message = str(details.get("message", event.replace("_", " ")))
        item.setText(3, message)
        item.setToolTip(3, message)
        if event in {"ping", "ping_failed"}:
            result = f"{item.text(1)}: {message}"
            self.ping_status_label.setText(result)
            self.status_label.setText(result)
            self._log(result)
        elif event in {"error", "disconnected", "progress", "link_diagnostic"}:
            self._log(f"{item.text(1)}: {message}")
        elif event in {"identified", "stopped", "operation", "typing_complete", "typing_canceled"}:
            self._log(f"{item.text(1)}: {message}")

    def _operation_error(self, address: str, error: object) -> None:
        item = self.items.get(address)
        name = item.text(1) if item is not None else address
        message = safe_error(error) if isinstance(error, BaseException) else str(error)
        logger.error("UI operation error address=%s message=%s", address, message)
        if item is not None:
            item.setText(3, f"Failed: {message}")
        self._log(f"{name}: failed — {message}")
        self.status_label.setText(f"Operation failed for {name}")

    def _task_failed(self, message: str) -> None:
        logger.error("UI task failed message=%s", message)
        self.scan_button.setEnabled(True)
        self.status_label.setText(f"Failed: {message}")
        self._log(f"Operation failed: {message}")

    def closeEvent(self, event: QCloseEvent) -> None:
        self._cancel_delivery("Application closed")
        for dialog in tuple(self.passkey_dialogs.values()):
            dialog.reject()
        logger.info("Main window closing")
        self._release_boards()
        event.accept()

    def _release_boards(self) -> None:
        """Disconnect every board before exit, keeping the window responsive and explaining any wait."""
        controller = self.controller
        busy = (any(session.state.connected for session in controller.sessions.values())
                or controller.connect_tasks or controller.repair_tasks)
        if not busy:
            self.runner.close(controller)  # nothing to wait for
            return
        loop = QEventLoop(self)
        self.bridge.shutdown_done.connect(loop.quit)

        def work() -> None:
            try:
                self.runner.close(controller)
            finally:
                self.bridge.shutdown_done.emit()
        threading.Thread(target=work, name="wits-shutdown", daemon=True).start()
        notice = ClosingNotice(self)
        QTimer.singleShot(400, lambda: (notice.show(), setattr(self, "closing_notice_shown", True)))
        QTimer.singleShot((SHUTDOWN_TIMEOUT_S + 2) * 1000, loop.quit)  # never hang on exit
        loop.exec()
        notice.close()
        self.bridge.shutdown_done.disconnect(loop.quit)


def _confirm_update(window: "MainWindow") -> None:
    previous = app_update.confirm_started()
    if previous:
        window._log(f"Updated to {__version__}. The previous version is still in {previous}; "
                    "delete that folder when you are satisfied.")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("WITS Deploy")
    # Match the installed desktop entry so Plasma can group and pin the app.
    from .runtime import DESKTOP_ID
    app.setDesktopFileName(DESKTOP_ID)
    app.setOrganizationName("Whitehorse IT Solutions")
    window = MainWindow()
    window.show()
    window.start_release_check()
    QTimer.singleShot(15000, lambda: _confirm_update(window))
    return app.exec()
