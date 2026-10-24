"""Offline startup check for standalone artifacts; never connects to hardware."""
import importlib
import json
from pathlib import Path
import subprocess
import sys
from . import __version__
from .runtime import frozen, worker_command
from .firmware_bundle import bundled_manifest
from .firmware_update import BOARD_CODES, load_release


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
            help_check = subprocess.run(worker_command("esptool", "--help"), capture_output=True,
                                        text=True, encoding="utf-8", timeout=30,
                                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            if help_check.returncode or "write-flash" not in help_check.stdout:
                raise RuntimeError("Bundled esptool CLI did not start correctly")
        result["ok"] = True
    except Exception as error:
        result["error"] = str(error)
    Path(output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if result["ok"] else 1
