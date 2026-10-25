"""Offline startup check for standalone artifacts; never connects to hardware."""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
from . import __version__
from .runtime import frozen, worker_command
from .firmware_bundle import bundled_manifest
from .firmware_update import BOARD_CODES, load_release


def esptool_help(extra_environment=None, stdin=subprocess.DEVNULL, *arguments):
    """Run the bundled esptool the way the USB flasher does and return (exit code, text)."""
    completed = subprocess.run(
        worker_command("esptool", *(arguments or ("--help",))), stdin=stdin,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
        errors="replace", timeout=30, env=dict(os.environ, **(extra_environment or {})),
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    return completed.returncode, completed.stdout or ""


def esptool_diagnostics():
    """Try a few variants so one failing run explains why esptool printed nothing."""
    variants = {
        "flasher-style": dict(),
        "inherited-stdin": dict(stdin=None),
        "no-color": dict(extra_environment={"NO_COLOR": "1", "TERM": "dumb"}),
        "utf8": dict(extra_environment={"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}),
        "version-command": dict(arguments=("version",)),
    }
    report = {}
    for name, options in variants.items():
        try:
            code, text = esptool_help(options.get("extra_environment"),
                                      options.get("stdin", subprocess.DEVNULL), *options.get("arguments", ()))
            report[name] = dict(exit=code, characters=len(text), start=text[:80])
        except Exception as error:
            report[name] = dict(error=str(error))
    return report


def main(output):
    result = dict(version=__version__, frozen=frozen(), ok=False)
    try:
        from PySide6.QtWidgets import QApplication, QPushButton
        from PySide6.QtSerialPort import QSerialPortInfo
        import bleak
        backend = "winrt" if sys.platform == "win32" else "bluezdbus"
        importlib.import_module(f"bleak.backends.{backend}.client")
        application = QApplication.instance() or QApplication([])
        button = QPushButton("WITS Deploy")
        application.processEvents()
        button.close()
        result["serial_ports"] = len(QSerialPortInfo.availablePorts())
        if frozen():
            manifest = bundled_manifest()
            if manifest is None:
                raise RuntimeError("The included firmware release is missing")
            release = load_release(manifest)
            if {target.board for target in release.targets} != set(BOARD_CODES):
                raise RuntimeError("The included firmware release is incomplete")
            for target in release.targets:
                release.select(target.board)
                release.select(target.board, factory=True)
            result["firmware_version"] = release.version
            helper = worker_command("--self-test")
            check = subprocess.run(helper, capture_output=True, text=True, encoding="utf-8", timeout=30,
                                   creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            if check.returncode:
                raise RuntimeError(check.stdout + check.stderr)
            result["helper"] = json.loads(check.stdout)
            code, help_text = esptool_help()
            if code or "write-flash" not in help_text:
                result["esptool_diagnostics"] = esptool_diagnostics()
                raise RuntimeError(f"Bundled esptool CLI did not start correctly: "
                                   f"exit={code} output={help_text[-400:]!r}")
        result["ok"] = True
    except Exception as error:
        result["error"] = str(error)
    Path(output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if result["ok"] else 1
