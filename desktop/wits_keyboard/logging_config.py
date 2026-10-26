"""Diagnostic logging that never records keyboard payload bytes."""

from __future__ import annotations

import logging
import os
import platform
import re
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from . import __version__
from .runtime import log_directory

LOG_DIRECTORY = log_directory()
LOG_PATH = LOG_DIRECTORY / "wits-keyboard-debug.log"

_SENSITIVE_MARKERS = (
    "write characteristic",
    "could not write value",
)
_BUFFER_PATTERN = re.compile(
    r"(?:bytearray|bytes|memoryview)\s*\([^\n]*\)", re.IGNORECASE
)


def safe_error(error: BaseException) -> str:
    """Return an operator-facing error without a possible GATT payload."""
    message = str(error)
    if not message:
        if isinstance(error, TimeoutError):
            return "operation timed out"
        return type(error).__name__
    lowered = message.casefold()
    if any(marker in lowered for marker in _SENSITIVE_MARKERS):
        return f"BLE write failed ({type(error).__name__}); payload omitted"
    return _BUFFER_PATTERN.sub("<buffer omitted>", message)


class PayloadRedactionFilter(logging.Filter):
    """Strip third-party DEBUG messages that may contain submitted text."""

    def filter(self, record: logging.LogRecord) -> bool:
        rendered = record.getMessage()
        lowered = rendered.casefold()
        if any(marker in lowered for marker in _SENSITIVE_MARKERS):
            record.msg = "BLE write diagnostic: payload omitted"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            return True

        if record.exc_info is not None:
            exception_message = str(record.exc_info[1]).casefold()
            if any(marker in exception_message for marker in _SENSITIVE_MARKERS):
                record.msg = f"{rendered} [exception payload omitted]"
                record.args = ()
                record.exc_info = None
                record.exc_text = None
        return True


def _uncaught_exception(
    exception_type: type[BaseException],
    exception: BaseException,
    traceback: Any,
) -> None:
    logging.getLogger("wits_keyboard.uncaught").critical(
        "Uncaught application exception",
        exc_info=(exception_type, exception, traceback),
    )


def _thread_exception(args: threading.ExceptHookArgs) -> None:
    logging.getLogger("wits_keyboard.uncaught").critical(
        "Uncaught thread exception thread=%s",
        args.thread.name if args.thread is not None else "unknown",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


def configure_logging() -> Path:
    """Enable application and Bleak DEBUG logging to a rotating local file."""
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=4 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s.%(msecs)03d %(levelname)-8s "
            "%(threadName)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler.addFilter(PayloadRedactionFilter())

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for existing in tuple(root.handlers):
        root.removeHandler(existing)
        existing.close()
    root.addHandler(handler)

    # Bleak's connection, pairing, service-discovery, and BlueZ traces are
    # valuable here. Its raw write diagnostics are removed by the filter.
    logging.getLogger("bleak").setLevel(logging.DEBUG)
    logging.getLogger("dbus_fast").setLevel(logging.INFO)
    logging.captureWarnings(True)
    sys.excepthook = _uncaught_exception
    threading.excepthook = _thread_exception

    try:
        os.chmod(LOG_PATH, 0o600)
    except OSError:
        pass

    logger = logging.getLogger("wits_keyboard.startup")
    logger.info("=" * 72)
    logger.info(
        "Starting WITS Deploy version=%s python=%s platform=%s",
        __version__,
        platform.python_version(),
        platform.platform(),
    )
    logger.info("Diagnostic log=%s", LOG_PATH)
    logger.info("Started from executable=%s launched by %s", sys.executable, _parent_command())
    return LOG_PATH


def _parent_command() -> str:
    """The command line of the process that started this one (Linux), to explain which launcher ran it."""
    try:
        raw = Path(f"/proc/{os.getppid()}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        return f"pid {os.getppid()}: {raw.strip()[:160]}"
    except OSError:
        return f"pid {os.getppid()}"
