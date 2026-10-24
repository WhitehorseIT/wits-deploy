#!/usr/bin/env python3
"""Promote checked firmware bytes and package a stable controller release."""

import argparse
import ast
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("--promote-from", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        parser.error("stable version must be MAJOR.MINOR.PATCH")
    if not re.fullmatch(r"[0-9A-Za-z.-]+", args.promote_from):
        parser.error("invalid source release name")

    project = Path(__file__).resolve().parents[1]
    source = project / "desktop"
    module = ast.parse((source / "wits_keyboard" / "__init__.py").read_text())
    app_version = next((ast.literal_eval(node.value) for node in module.body
                        if isinstance(node, ast.Assign) and any(
                            isinstance(target, ast.Name) and target.id == "__version__"
                            for target in node.targets)), None)
    if app_version != args.version:
        parser.error(f"app version {app_version!r} does not match release {args.version!r}")
    firmware_source = project / "releases" / "firmware" / args.promote_from / "tqtpro"
    release = project / "releases" / "firmware" / args.version / "tqtpro"
    archive_path = release / f"WITS-Keyboard-{args.version}.zip"
    if archive_path.exists():
        parser.error("stable archive already exists; use a new release version")
    for name in ("README-FIRST.txt", "RELEASE-NOTES.md"):
        if not (release / name).is_file():
            parser.error(f"prepare {release / name} first")

    checksums = {}
    for line in (firmware_source / "SHA256SUMS.txt").read_text().splitlines():
        sha, filename = line.split("  ", 1)
        checksums[filename] = sha
    release.mkdir(parents=True, exist_ok=True)
    firmware_files = []
    for kind in ("app", "factory"):
        old_name = f"WITS-Keyboard-{args.promote_from}.{kind}.bin"
        original = firmware_source / old_name
        if digest(original.read_bytes()) != checksums.get(old_name):
            raise RuntimeError(f"source firmware checksum failed: {old_name}")
        promoted = release / f"WITS-Keyboard-{args.version}.{kind}.bin"
        shutil.copyfile(original, promoted)
        if promoted.read_bytes() != original.read_bytes():
            raise RuntimeError("firmware promotion changed binary bytes")
        firmware_files.append(promoted)
    (release / "SHA256SUMS.txt").write_text("".join(
        f"{digest(path.read_bytes())}  {path.name}\n" for path in firmware_files
    ))
    for name in ("flash-windows.cmd", "FLASHING-INSTRUCTIONS.txt"):
        shutil.copyfile(project / "scripts" / name, release / name)

    entries = {}
    def add(path, name):
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"expected regular file: {path}")
        data = path.read_bytes()
        if path.suffix == ".cmd":
            data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        entries[name] = data

    for name in ("README-FIRST.txt", "RELEASE-NOTES.md"):
        add(release / name, name)
    for name in ("run.py", "requirements.txt", "requirements-release.txt", "README.md",
                 "SETUP-WINDOWS.cmd", "START-WINDOWS.cmd", "SETUP-LINUX.sh", "START-LINUX.sh"):
        add(source / name, f"app/{name}")
    for directory in ("wits_keyboard", "tests"):
        for path in sorted((source / directory).glob("*.py")):
            add(path, "app/" + path.relative_to(source).as_posix())
    for path in firmware_files:
        add(path, "firmware/" + path.name)
    for name in ("SHA256SUMS.txt", "flash-windows.cmd", "FLASHING-INSTRUCTIONS.txt"):
        add(release / name, "firmware/" + name)

    metadata = {
        "version": args.version,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "firmware_promoted_from": args.promote_from,
        "firmware_rebuilt": False,
        "application": "Python source; Windows/Linux; Python 3.11+",
        "direct_dependencies": (source / "requirements-release.txt").read_text().splitlines(),
        "sha256": {name: digest(data) for name, data in entries.items()},
    }
    entries["MANIFEST.json"] = (json.dumps(metadata, indent=2) + "\n").encode()
    entries["SHA256SUMS.txt"] = "".join(
        f"{digest(data)}  {name}\n" for name, data in sorted(entries.items())
    ).encode()
    root = f"WITS-Keyboard-{args.version}/"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            entry = ZipInfo(root + name)
            entry.create_system = 3
            entry.external_attr = (0o100755 if name.endswith(".sh") else 0o100644) << 16
            entry.compress_type = ZIP_DEFLATED
            archive.writestr(entry, data)
    with ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("archive integrity check failed")
        for name, data in entries.items():
            if archive.read(root + name) != data:
                raise RuntimeError(f"packaging mismatch: {name}")
            if name.endswith(".py"):
                compile(data, name, "exec")
    (release / "MANIFEST.json").write_text(json.dumps(metadata, indent=2) + "\n")
    archive_sha = digest(archive_path.read_bytes())
    archive_path.with_suffix(".zip.sha256").write_text(f"{archive_sha}  {archive_path.name}\n")
    print(archive_path)
    print(f"{len(entries)} files; {archive_path.stat().st_size:,} bytes")
    print(f"SHA-256: {archive_sha}")
    print("Firmware unchanged; source checksums, archive integrity and Python syntax verified")


if __name__ == "__main__":
    main()
