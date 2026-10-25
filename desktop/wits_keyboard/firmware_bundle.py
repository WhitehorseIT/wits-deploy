"""Locate the included release and validate firmware before packaging it."""
import json
from pathlib import Path
import re
import sys
from .firmware_update import BOARD_CODES, load_release
from .runtime import frozen


def bundled_manifest():
    if frozen():
        path = Path(sys._MEIPASS) / "firmware" / "release.ota.json"
        return path if path.is_file() else None
    desktop = Path(__file__).resolve().parents[1]
    pointer = desktop / "packaging" / "firmware-release.txt"
    if not pointer.is_file():
        return None
    version = pointer.read_text().strip()
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.-]*", version):
        return None
    folder = desktop.parent / "releases" / "firmware" / version
    # Releases from 0.2.0-dev18 use the WITS-Deploy prefix; older ones keep WITS-Keyboard.
    path = next((folder / name for name in (f"WITS-Deploy-Release-{version}.ota.json",
                                            f"WITS-Keyboard-Release-{version}.ota.json")
                 if (folder / name).is_file()), None)
    if path is None:
        return None
    release = load_release(path)
    # Source clones track manifests but not binaries. Leave manual selection
    # available until a complete release is present.
    for target in release.targets:
        if not target.factory or not (path.parent / target.filename).is_file() or not (path.parent / target.factory.filename).is_file():
            return None
    return path


def stage_release(manifest, destination):
    release = load_release(manifest)
    if {target.board for target in release.targets} != set(BOARD_CODES):
        raise ValueError("The included release must contain firmware for all three board models")
    entries, images = {}, {}
    for target in release.targets:
        app = release.select(target.board)
        factory = release.select(target.board, factory=True)
        if factory.data[0x10000:] != app.data:
            raise ValueError(f"Factory/app image mismatch for {target.board}")
        entries[app.filename], entries[factory.filename] = app.data, factory.data
        images[target.board] = dict(chip="esp32s3", filename=app.filename,
            size=len(app.data), sha256=app.sha256,
            factory=dict(filename=factory.filename, size=len(factory.data), sha256=factory.sha256))
    # Finish all image/hash/model validation before writing any staging files.
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in entries.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    path = destination / "release.ota.json"
    path.write_text(json.dumps(dict(schema=2, firmware=release.version, images=images), indent=2) + "\n")
    return load_release(path)
