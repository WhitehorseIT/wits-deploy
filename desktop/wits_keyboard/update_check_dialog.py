"""The Check for updates dialog: look for the newest release, firmware and (optionally) development snapshot, and
install the one that applies to how this copy of the app runs."""
from __future__ import annotations

import threading
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout)

from . import __version__, app_update, online_release, release_check, source_update, version_label, build_id
from .logging_config import safe_error

INCLUDE_SNAPSHOTS_KEY = "updates/include_snapshots"


@dataclass
class Plan:
    lines: list[str]
    action: str = "none"          # "none", "source" (stage and restart) or "app" (the packaged Linux updater)
    action_text: str = ""
    note: str = ""                # why an update that exists cannot be installed here
    choice: object = None         # the source_update.Choice for "source"


def gather() -> dict:
    """Everything the dialog needs from GitHub: signed manifests only; None for what is missing."""
    tags = online_release.fetch_listing()
    if tags is None:
        return {"offline": True}
    result = {"offline": False, "tags": tags}
    for kind in online_release.KINDS:
        result[kind] = online_release.latest_signed(kind=kind, tags=tags)
    result["snapshot"] = None
    if online_release.SNAPSHOT_TAG in tags:
        try:
            result["snapshot"] = online_release.fetch_snapshot()
        except Exception:
            result["snapshot"] = None
    return result


def plan(result: dict, include_snapshots: bool, *, current_version: str = __version__, current_build: str | None = None,
         source_reason: str | None = None, app_reason_for=None) -> Plan:
    """Turn what was found into text and one possible action. Pure, so it can be tested without a window."""
    build = build_id() if current_build is None else current_build
    here = f"This app: {current_version}" + (f" (build {build})" if build else "")
    if result.get("offline"):
        return Plan([here, "Could not reach GitHub. Check the internet connection and try again."])
    app, firmware, snapshot = result.get("app"), result.get("firmware"), result.get("snapshot")
    lines = [here]
    if app is None:
        lines.append("Latest release: none found with a verified signature")
    else:
        newer = release_check.parse_version(app.version) > release_check.parse_version(current_version)
        lines.append(f"Latest release: {app.version}" + (" - an update is available" if newer else " - you are up to date"))
    lines.append(f"Latest firmware: {firmware.version} (signed)" if firmware else "Latest firmware: none found")
    if include_snapshots:
        lines.append(f"Development snapshot: {snapshot.commit[:7]} (signed)" if snapshot
                     else "Development snapshot: none found")
    # What can be installed depends on how this copy runs.
    if app_reason_for is not None:                                  # the packaged Linux build
        reason = app_reason_for(app)
        if reason is None:
            return Plan(lines, "app", f"Update app to {app.version}…")
        return Plan(lines, note="" if app is None or reason.startswith("This is already") else reason)
    choice = source_update.choose(app, snapshot, include_snapshots, current_version, build)
    if choice is None:
        return Plan(lines)
    if source_reason is not None:
        return Plan(lines, note=f"An update is available ({choice.summary}), but: {source_reason}", choice=choice)
    return Plan(lines, "source", f"Update to {choice.summary}", choice=choice)


class _Relay(QObject):
    """Signals the worker threads emit; threads never hold the dialog widget itself."""
    checked = Signal(object)
    progress = Signal(int, int)
    staged = Signal(object, str)   # pending-update info or None, message


class UpdateCheckDialog(QDialog):
    def __init__(self, settings, parent=None, *, packaged_linux: bool = False) -> None:
        super().__init__(parent)
        self.settings = settings
        self.packaged_linux = packaged_linux
        self.install_requested: str | None = None   # "source": staged, restart now; "app": hand over to Update app
        self.cancelled = threading.Event()
        self.busy = False
        self.current_plan = Plan([])
        self.result: dict = {}
        self._relay = _Relay()
        self._relay.checked.connect(self._checked)
        self._relay.progress.connect(self._progress)
        self._relay.staged.connect(self._staged)
        self.setWindowTitle("Check for updates")
        self.resize(560, 300)
        layout = QVBoxLayout(self)
        self.summary = QLabel("Checking…")
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.snapshots = QCheckBox("Include development builds (signed snapshots of the latest changes)")
        self.snapshots.setChecked(str(settings.value(INCLUDE_SNAPSHOTS_KEY, "false")).lower() in ("true", "1"))
        self.snapshots.toggled.connect(self._snapshots_toggled)
        layout.addWidget(self.snapshots)
        self.note = QLabel("")
        self.note.setTextFormat(Qt.TextFormat.PlainText)
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        layout.addWidget(self.bar)
        row = QHBoxLayout()
        self.again = QPushButton("Check again")
        self.again.clicked.connect(self.start_check)
        self.install = QPushButton("Update")
        self.install.setEnabled(False)
        self.install.clicked.connect(self._install)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self._cancel_or_close)
        for button in (self.again, self.install, self.close_button):
            row.addWidget(button)
        layout.addLayout(row)
        self.start_check()

    def start_check(self) -> None:
        self.summary.setText("Checking…")
        self.note.setText("")
        self.install.setEnabled(False)
        relay = self._relay
        threading.Thread(target=lambda: relay.checked.emit(gather()), name="wits-update-check", daemon=True).start()

    def _checked(self, result: dict) -> None:
        self.result = result
        self._render()

    def _snapshots_toggled(self, on: bool) -> None:
        self.settings.setValue(INCLUDE_SNAPSHOTS_KEY, "true" if on else "false")
        if self.result:
            self._render()

    def _render(self) -> None:
        self.current_plan = plan(
            self.result, self.snapshots.isChecked(),
            source_reason=None if self.packaged_linux else source_update.unavailable_reason(),
            app_reason_for=app_update.unavailable_reason if self.packaged_linux else None)
        self.summary.setText("\n".join(self.current_plan.lines))
        self.note.setText(self.current_plan.note)
        self.install.setText(self.current_plan.action_text or "Update")
        self.install.setEnabled(self.current_plan.action != "none" and not self.busy)

    def _install(self) -> None:
        action = self.current_plan.action
        if action == "app":
            self.install_requested = "app"
            self.accept()
            return
        if action != "source":
            return
        self.busy = True
        self.cancelled.clear()
        self.install.setEnabled(False)
        self.again.setEnabled(False)
        self.snapshots.setEnabled(False)
        self.close_button.setText("Cancel")
        self.bar.setVisible(True)
        self.note.setText("Downloading and verifying…")
        choice, relay, cancelled = self.current_plan.choice, self._relay, self.cancelled

        def work() -> None:
            try:
                info = source_update.stage(choice, progress=relay.progress.emit, cancelled=cancelled)
                relay.staged.emit(info, "")
            except InterruptedError:
                relay.staged.emit(None, "Canceled; nothing was changed.")
            except Exception as error:
                relay.staged.emit(None, safe_error(error))

        threading.Thread(target=work, name="wits-source-download", daemon=True).start()

    def _progress(self, done: int, total: int) -> None:
        self.bar.setMaximum(max(total, 1))
        self.bar.setValue(done)

    def _staged(self, info, message: str) -> None:
        self.busy = False
        self.close_button.setText("Close")
        self.close_button.setEnabled(True)
        self.again.setEnabled(True)
        self.snapshots.setEnabled(True)
        self.bar.setVisible(False)
        if info is None:
            self.note.setText("Update failed; nothing was changed. " + message)
            self._render()
            return
        self.note.setText("Verified. Restarting to install…")
        self.install_requested = "source"
        self.accept()

    def _cancel_or_close(self) -> None:
        if self.busy:
            self.cancelled.set()
            self.close_button.setEnabled(False)
        else:
            self.reject()

    def reject(self) -> None:
        if not self.busy:
            super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        event.ignore() if self.busy else super().closeEvent(event)
