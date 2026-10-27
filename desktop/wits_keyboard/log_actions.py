"""Copy and save buttons for any text log window."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QApplication, QHBoxLayout, QMessageBox, QPushButton


def save_text(parent, title: str, text: str, suggested_name: str, settings=None) -> str:
    """Ask where to save ``text`` and write it as UTF-8. Returns the path, or an empty string if cancelled or
    the file could not be written (the user is told why)."""
    from .file_choice import choose_save_path
    path = choose_save_path(parent, title, suggested_name, "Text file (*.txt)", settings)
    if not path:
        return ""
    try:
        Path(path).write_text(text, encoding="utf-8")
    except OSError as error:
        QMessageBox.warning(parent, "Could not save", f"The file could not be saved: {error}")
        return ""
    return path


def log_buttons(parent, get_text, name: str, on_done=None) -> QHBoxLayout:
    """A row with Copy and Save buttons for the text returned by ``get_text()``. ``on_done(message)`` is called after
    a copy or save so the caller can show it. ``name`` is used for the suggested file name."""
    row = QHBoxLayout()
    copy = QPushButton("Copy output")
    copy.setToolTip("Copy this output to the clipboard")
    save = QPushButton("Save output…")
    save.setToolTip("Save this output to a text file, for sending to support")

    def do_copy() -> None:
        text = get_text()
        QApplication.clipboard().setText(text)
        if on_done:
            on_done(f"Copied {len(text.splitlines())} lines to the clipboard")

    def do_save() -> None:
        path = save_text(parent, "Save output", get_text(), f"{name}-{datetime.now():%Y%m%d-%H%M%S}.txt")
        if path and on_done:
            on_done(f"Saved to {path}")

    copy.clicked.connect(do_copy)
    save.clicked.connect(do_save)
    row.addWidget(copy)
    row.addWidget(save)
    row.addStretch(1)
    row.copy_button, row.save_button = copy, save  # for tests
    return row
