#!/usr/bin/env python3
"""Combine verified model manifests into one local OTA release manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop"))
from wits_keyboard.firmware_update import load_release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", type=Path)
    args = parser.parse_args()
    root = args.release.resolve()
    version = root.name
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.-]*", version):
        parser.error("invalid release folder name")
    # Releases from 0.2.0-dev18 use the WITS-Deploy prefix; older ones keep WITS-Keyboard.
    names = {
        "tqtpro": (f"WITS-Deploy-TQTPro-{version}.ota.json", f"WITS-Keyboard-{version}.ota.json"),
        "waveshare7": (f"WITS-Deploy-Waveshare7-{version}.ota.json", f"WITS-Keyboard-Waveshare7-{version}.ota.json"),
        "waveshare147": (f"WITS-Deploy-Waveshare147-{version}.ota.json", f"WITS-Keyboard-Waveshare147-{version}.ota.json"),
    }
    paths = {}
    for board, candidates in names.items():
        found = next((root / board / name for name in candidates if (root / board / name).is_file()), None)
        if found:
            paths[board] = found
    legacy = bool(paths) and all(path.name.startswith("WITS-Keyboard-") for path in paths.values())
    if not paths:
        parser.error("no supported model manifests found")
    images = {}
    for board, path in paths.items():
        release = load_release(path)
        if release.version != version or len(release.targets) != 1 or release.targets[0].board != board:
            parser.error(f"model/version mismatch: {path}")
        image = release.select(board)  # Verify the real binary before publishing its descriptor.
        images[board] = dict(chip="esp32s3", filename=(path.parent / image.filename).relative_to(root).as_posix(),
                             size=len(image.data), sha256=image.sha256)
        factory = path.parent / image.filename.replace(".app.bin", ".factory.bin")
        data = factory.read_bytes()
        sums = dict(line.split("  ", 1)[::-1] for line in (path.parent / "SHA256SUMS.txt").read_text().splitlines())
        digest = hashlib.sha256(data).hexdigest()
        if digest != sums.get(factory.name):
            parser.error(f"factory checksum mismatch: {factory}")
        images[board]["factory"] = dict(filename=factory.relative_to(root).as_posix(), size=len(data), sha256=digest)
    text = json.dumps(dict(schema=2, firmware=version, images=images), indent=2) + "\n"
    output = root / (f"WITS-Keyboard-Release-{version}.ota.json" if legacy else f"WITS-Deploy-Release-{version}.ota.json")
    if output.exists():
        if output.read_text() != text:
            parser.error("refusing to replace an existing release catalog with different contents")
    else:
        with output.open("x") as stream:
            stream.write(text)
    verified = load_release(output)
    for board in images:
        verified.select(board, factory=True)
    print(output)


if __name__ == "__main__":
    main()
