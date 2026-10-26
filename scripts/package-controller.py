#!/usr/bin/env python3
"""Create an app-only distribution for the tester without logs, settings or firmware."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    project = Path(__file__).resolve().parents[1]
    source = project / "desktop"
    module = ast.parse((source / "wits_keyboard/__init__.py").read_text())
    version = next(ast.literal_eval(node.value) for node in module.body
                   if isinstance(node, ast.Assign) and any(
                       isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets))
    release = project / "releases/desktop" / version
    archive_path = release / f"WITS-Deploy-App-{version}.zip"
    if archive_path.exists():
        raise RuntimeError("Existing app archive is immutable; use a new version")
    entries = {"README-FIRST.txt": (release / "README-FIRST.txt").read_bytes()}
    paths = [source / name for name in (
        "run.py", "requirements.txt", "requirements-release.txt", "README.md",
        "SETUP-LINUX.sh", "START-LINUX.sh", "INSTALL-LAUNCHER-LINUX.sh")]
    windows_start = project / "WINDOWS-START.cmd"  # the single Windows launcher sits at the top of the archive
    entries["WINDOWS-START.cmd"] = windows_start.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    paths += sorted((source / "wits_keyboard").glob("*.py"))
    paths += sorted((source / "tests").glob("*.py"))
    paths.append(source / "packaging" / "firmware-release.txt")
    for path in paths:
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"Expected regular file: {path}")
        data = path.read_bytes()
        if path.suffix == ".cmd":
            data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        entries["app/" + path.relative_to(source).as_posix()] = data
    manifest = dict(version=version, created_utc=datetime.now(timezone.utc).isoformat(),
                    application="Python source; Windows/Linux; Python 3.11+",
                    firmware_included=False, tester_existing_firmware="T-QT Pro 0.1.1",
                    direct_dependencies=(source / "requirements-release.txt").read_text().splitlines(),
                    sha256={name: sha(data) for name, data in entries.items()})
    entries["MANIFEST.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    entries["SHA256SUMS.txt"] = "".join(f"{sha(data)}  {name}\n" for name, data in sorted(entries.items())).encode()
    root = f"WITS-Deploy-App-{version}/"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            entry = ZipInfo(root + name)
            entry.create_system = 3
            entry.external_attr = (0o100755 if name.endswith(".sh") else 0o100644) << 16
            entry.compress_type = ZIP_DEFLATED
            archive.writestr(entry, data)
    with ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        for name, data in entries.items():
            assert archive.read(root + name) == data
            if name.endswith(".py"):
                compile(data, name, "exec")
    digest = sha(archive_path.read_bytes())
    archive_path.with_suffix(".zip.sha256").write_text(f"{digest}  {archive_path.name}\n")
    print(archive_path)
    print(f"{len(entries)} files; {archive_path.stat().st_size:,} bytes; SHA-256 {digest}")


if __name__ == "__main__":
    main()
