"""Paths and child-process commands for source and standalone distributions."""
import os
from pathlib import Path
import sys

WORKER_NAME = "WITS-Deploy-Worker"
DESKTOP_ID = "com.whitehorseit.WITSDeploy"


def frozen():
    return bool(getattr(sys, "frozen", False))


def app_directory():
    executable = Path(sys.executable)
    if frozen():
        if executable.stem == WORKER_NAME:
            return executable.parent.parent.parent
        return executable.parent
    return Path(__file__).resolve().parents[1]


def worker_command(tool, *arguments):
    if frozen():
        suffix = ".exe" if sys.platform == "win32" else ""
        executable = app_directory() / "helpers" / WORKER_NAME / (WORKER_NAME + suffix)
        if not executable.is_file():
            raise RuntimeError("The USB helper is missing. Extract the complete WITS Deploy package again.")
        return [str(executable), tool, *arguments]
    modules = {"usb-flash": "wits_keyboard.usb_flash", "esptool": "esptool"}
    return [sys.executable, "-u", "-m", modules[tool], *arguments]


def log_directory():
    if not frozen():
        return app_directory() / "logs"
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "Whitehorse IT Solutions" / "WITS Deploy" / "logs"
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return root / "wits-deploy" / "logs"
