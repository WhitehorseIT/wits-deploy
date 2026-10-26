#!/usr/bin/env python3
"""Download a published firmware release, verify its signature and checksums, and print the .ota.json path.

Used by the app release workflow so the app bundles exactly the firmware that was published and
signed, not a fresh rebuild.
"""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop"))
from wits_keyboard import online_release as online


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="firmware version, e.g. 1.0.0-rc1 (release tag fw-v<version>)")
    parser.add_argument("--out", type=Path, required=True, help="folder to unpack the release into")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:  # trust state lives here so CI never keeps any
        release = online.fetch_signed(args.version, state=online.TrustState(Path(scratch)), kind="firmware")
        manifest = online.download_firmware(release, directory=args.out)
    print(manifest)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        sys.exit(f"Could not fetch firmware release: {error}\nPublish the firmware release (tag fw-v<version>) first.")
