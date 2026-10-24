#!/usr/bin/env python3
"""Flash the Waveshare prototype, checking the port, image hash and flash size."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", nargs="?", help="e.g. /dev/ttyACM0 or /dev/ttyUSB0")
    parser.add_argument("--version", default="0.2.0-dev9", help="firmware release (default: 0.2.0-dev9)")
    parser.add_argument("--app-only", action="store_true", help="update application at 0x10000, keeping existing bonds")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.-]*", args.version):
        parser.error("invalid firmware version")
    project = Path(__file__).resolve().parents[1]
    release = project / "releases" / "firmware" / args.version / "waveshare7"
    kind = "app" if args.app_only else "factory"
    image = release / f"WITS-Keyboard-Waveshare7-{args.version}.{kind}.bin"
    expected = dict(line.split("  ", 1)[::-1] for line in
                    (release / "SHA256SUMS.txt").read_text().splitlines())
    if hashlib.sha256(image.read_bytes()).hexdigest() != expected.get(image.name):
        parser.error("firmware checksum failed")
    port = args.port
    if not port:
        from serial.tools import list_ports
        candidates = [p for p in list_ports.comports() if p.vid in (0x303a, 0x1a86, 0x10c4)]
        if len(candidates) != 1:
            for p in candidates:
                print(f"  {p.device}: {p.description}")
            parser.error("could not select one board; rerun with its serial port as an argument")
        port = candidates[0].device
    tool = Path.home() / ".platformio/packages/tool-esptool/esptool"
    common = [str(tool), "--chip", "esp32s3", "--port", port, "--baud", "460800"]
    print(f"Checking ESP32-S3 on {port} before flashing Waveshare firmware...", flush=True)
    result = subprocess.run(common + ["--after", "no-reset", "flash-id"], capture_output=True, text=True)
    print(result.stdout, end="", flush=True)
    print(result.stderr, end="", file=sys.stderr, flush=True)
    if result.returncode:
        return result.returncode
    match = re.search(r"Detected flash size:\s*(\d+)\s*MB", result.stdout)
    if not match or int(match[1]) < 8:
        parser.error("this image requires at least 8MB flash; refusing upload (do not use it on a T-QT Pro)")
    offset = "0x10000" if args.app_only else "0x0"
    result = subprocess.run(common + ["write-flash", offset, str(image)])
    if result.returncode:
        return result.returncode
    print("Press RESET. Expect the WITS programming screen; hold its HID control for 2 seconds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
