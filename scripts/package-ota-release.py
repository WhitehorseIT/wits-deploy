#!/usr/bin/env python3
"""Package one release manifest and its app images for every supported model."""
import argparse
import hashlib
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop"))
from wits_keyboard.firmware_update import load_release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    manifest = args.manifest.resolve()
    release = load_release(manifest)
    archive = manifest.parent / f"WITS-Keyboard-Firmware-{release.version}.zip"
    if archive.exists():
        parser.error("existing archive is immutable; use a new release")
    entries = {manifest.name: manifest.read_bytes()}
    for target in release.targets:
        entries[target.filename] = release.select(target.board).data
        if target.factory:
            entries[target.factory.filename] = release.select(target.board, factory=True).data
    entries["README-FIRST.txt"] = (
        f"WITS Deploy firmware {release.version}\n\n"
        "Extract this entire ZIP, preserving its folders. Use desktop app dev10\n"
        "or newer. Connect and disarm one board, highlight it, then click\n"
        f"OTA Update and choose {manifest.name}.\n"
        "The app reads the connected board's model, selects its matching binary\n"
        "and checks its size/SHA-256 before sending. This same JSON serves\n"
        "T-QT Pro, Waveshare7 and Waveshare147. Do not move the JSON away from\n"
        "the image folders. Waveshare147 pairing/operation has been tested;\n"
        "storage/recovery tests remain pending. Read waveshare147/README-FIRST.txt.\n\n"
        "Safely eject writable USB storage first. Keep power connected. Successful\n"
        "uploads restart in PROGRAM; enter HID again and reconnect. Bluetooth\n"
        "OTA requires firmware dev8 or newer installed by USB first. Linux may\n"
        "need a one-time Re-pair after the old pre-OTA service layout changes.\n\n"
        "For USB flashing, use the app's USB Flash/Update button, select the same\n"
        "JSON, physical board model and serial port. Update working board writes\n"
        "the inactive slot and preserves pairings. Install blank board/factory\n"
        "recovery uses the factory image and clears existing board settings.\n"
        "Enter FLASH first. Waveshare7 uses UART; Waveshare147 and T-QT Pro\n"
        "use their native USB connector. Press RESET when verified.\n"
        "Never blindly serial-flash app0 at 0x10000: app1 may be selected.\n"
    ).encode()
    for target in release.targets:
        guide = manifest.parent / target.board / "README-FIRST.txt"
        if guide.is_file():
            entries[f"{target.board}/README-FIRST.txt"] = guide.read_bytes()
    entries["SHA256SUMS.txt"] = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(entries.items())).encode()
    with ZipFile(archive, "x", compression=ZIP_DEFLATED) as stream:
        for name, data in entries.items(): stream.writestr(name, data)
    with ZipFile(archive) as stream:
        assert stream.testzip() is None
        for name, data in entries.items(): assert stream.read(name) == data
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n")
    print(f"{archive}\n{archive.stat().st_size:,} bytes; SHA-256 {digest}")


if __name__ == "__main__": main()
