#!/usr/bin/env python3
"""Console helper kept separate from the windowed GUI for USB progress output."""
import json
import sys


def main():
    arguments = sys.argv[1:]
    if not arguments:
        raise SystemExit("Use usb-flash, esptool, install-launcher or --self-test")
    tool, *arguments = arguments
    sys.argv = [tool, *arguments]
    if tool == "usb-flash":
        from wits_keyboard.usb_flash import main as flash
        return flash()
    if tool == "esptool":
        import esptool
        esptool._main()  # The same entry point used by python -m esptool.
        return 0
    if tool == "install-launcher":
        from wits_keyboard.launcher import main as install
        return install()
    if tool == "--self-test":
        import esptool
        import serial
        from pathlib import Path
        from wits_keyboard.usb_flash import LAYOUTS
        # Stub JSON files must survive collection, not just the Python modules.
        if not list((Path(esptool.__file__).parent / "targets" / "stub_flasher").rglob("*.json")):
            raise RuntimeError("esptool stub data is missing")
        print(json.dumps(dict(esptool=esptool.__version__, serial=serial.__version__, boards=list(LAYOUTS))))
        return 0
    raise SystemExit(f"Unknown helper command: {tool}")


if __name__ == "__main__":
    raise SystemExit(main())
