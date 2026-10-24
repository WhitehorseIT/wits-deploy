#!/usr/bin/env python3
"""Describe one app-only image for the authenticated Bluetooth updater."""
import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("image", type=Path)
parser.add_argument("board", choices=("tqtpro", "waveshare7", "waveshare147"))
parser.add_argument("version")
args = parser.parse_args()
data = args.image.read_bytes()
if not args.image.name.endswith(".app.bin") or data[32:36] != bytes.fromhex("3254cdab"):
    parser.error("an ESP-IDF app-only image is required")
result = dict(schema=1, board=args.board, chip="esp32s3", firmware=args.version,
              filename=args.image.name, size=len(data), sha256=hashlib.sha256(data).hexdigest())
path = args.image.with_name(args.image.name.removesuffix(".app.bin") + ".ota.json")
path.write_text(json.dumps(result, indent=2) + "\n")
print(f"OTA manifest: {path}")
