"""Collect the app's logs into one ZIP that can be sent for analysis."""
from __future__ import annotations

import platform
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from . import __version__
from .runtime import data_directory, frozen


def suggested_name() -> str:
    return f"wits-deploy-logs-{datetime.now():%Y%m%d-%H%M%S}.zip"


def system_summary() -> str:
    return "\n".join((
        f"WITS Deploy {__version__}",
        f"Python {platform.python_version()} ({'packaged' if frozen() else 'source'})",
        f"Platform {platform.platform()}",
        f"Executable {sys.executable}",
        f"Saved {datetime.now().isoformat(timespec='seconds')}",
        "",
    ))


def build_bundle(destination: str | Path, event_lines, log_directory: str | Path) -> Path:
    """Write ``destination``: the on-screen events (oldest first), the debug logs, any crash traces and a
    system summary. GATT write payloads are already redacted in the logs."""
    destination, log_directory = Path(destination), Path(log_directory)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("system.txt", system_summary())
        bundle.writestr("event-log.txt", "\n".join(event_lines) + "\n")
        for path in sorted(log_directory.glob("wits-keyboard-debug.log*")) + sorted(log_directory.glob("crash-traces.log")):
            if path.is_file():
                bundle.write(path, path.name)
    return destination
