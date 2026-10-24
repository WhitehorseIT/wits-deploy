#!/usr/bin/env python3
"""First install or verified inactive-slot update for the Waveshare 1.47 TOUCH board."""
import argparse
from pathlib import Path
import re
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "desktop"))
from wits_keyboard.usb_flash import SerialFlasher


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", help="bootloader port, e.g. /dev/ttyACM0 or COM5")
    parser.add_argument("--version", default="0.2.0-dev13")
    parser.add_argument("--update", action="store_true",
                        help="preserve settings by updating the inactive slot of an existing WITS install")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.-]*", args.version):
        parser.error("invalid firmware version")
    folder = PROJECT / "releases" / "firmware" / args.version / "waveshare147"
    manifest = folder / f"WITS-Keyboard-Waveshare147-{args.version}.ota.json"
    # The individual descriptor also needs the factory descriptor for a safe
    # working-board partition-table comparison. Prefer the complete catalog.
    catalog = folder.parent / f"WITS-Keyboard-Release-{args.version}.ota.json"
    if catalog.is_file():
        manifest = catalog
    else:
        parser.error("complete release manifest is missing; build all targets first")
    print("Waveshare ESP32-S3-Touch-LCD-1.47 only (16MB flash).", flush=True)
    print("Mode: " + ("inactive-slot update" if args.update else "FACTORY INSTALL; existing settings are cleared"), flush=True)
    try:
        SerialFlasher(args.port).flash(manifest, "waveshare147", factory=not args.update)
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
