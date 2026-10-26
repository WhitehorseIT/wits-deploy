#!/usr/bin/env python3
"""Swap a staged update into place, or put the previous version back. Standard library only.

Run by WINDOWS-START.cmd while the app is NOT running (the app exits with code 75 to ask for an update), so no
file is in use. This script is deliberately not part of what an update replaces; change it rarely.

  apply_update.py apply      move .update/staged into place; keep the old files in .update/previous
  apply_update.py rollback   restore .update/previous (the new version failed before it confirmed itself)
"""
import json
import shutil
import sys
import time
from pathlib import Path

# What an update replaces. Everything else in this folder (.venv, logs, this script) is left alone.
REPLACED = ("wits_keyboard", "run.py", "worker.py", "requirements.txt", "requirements-release.txt",
            "requirements-build.txt", "README.md", "packaging", "tests")


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _move(source: Path, destination: Path, attempts: int = 4) -> None:
    """Move with a few retries: on Windows a virus scanner can briefly hold a freshly written file."""
    for attempt in range(attempts):
        try:
            shutil.move(str(source), str(destination))
            return
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.5)


def apply(root: Path) -> int:
    update, staged, previous = root / ".update", root / ".update" / "staged", root / ".update" / "previous"
    pending = update / "pending.json"
    if not pending.is_file() or not staged.is_dir():
        print("No update is waiting.")
        return 2
    if previous.exists():
        _remove(previous)
    previous.mkdir(parents=True)
    moved = []  # (name, had_old_copy)
    try:
        for name in REPLACED:
            new, old = staged / name, root / name
            if not new.exists():
                continue
            had_old = old.exists()
            if had_old:
                _move(old, previous / name)
            moved.append((name, had_old))
            _move(new, old)
    except Exception as error:
        print(f"Applying the update failed ({error}); restoring the previous files.")
        for name, had_old in reversed(moved):
            _remove(root / name)
            if had_old and (previous / name).exists():
                _move(previous / name, root / name)
        return 1
    (update / "applied.json").write_text(pending.read_text(encoding="utf-8"), encoding="utf-8")
    (update / "unconfirmed").write_text("The updated version has not yet confirmed that it runs.\n", encoding="utf-8")
    pending.unlink()
    shutil.rmtree(staged, ignore_errors=True)
    try:
        info = json.loads((update / "applied.json").read_text(encoding="utf-8"))
        print(f"Updated to {info.get('version', '?')} ({str(info.get('commit') or '')[:7]}).")
    except (OSError, ValueError):
        print("Update applied.")
    return 0


def rollback(root: Path) -> int:
    update, previous = root / ".update", root / ".update" / "previous"
    if not previous.is_dir():
        print("There is no previous version to restore.")
        (update / "unconfirmed").unlink(missing_ok=True)
        return 2
    for name in REPLACED:
        old = previous / name
        if old.exists():
            _remove(root / name)
            _move(old, root / name)
    (update / "unconfirmed").unlink(missing_ok=True)
    (update / "rolled-back").write_text("The previous version was restored.\n", encoding="utf-8")
    shutil.rmtree(previous, ignore_errors=True)
    print("Restored the previous version.")
    return 0


def main(argv) -> int:
    root = Path(__file__).resolve().parent
    if len(argv) == 2 and argv[1] == "apply":
        return apply(root)
    if len(argv) == 2 and argv[1] == "rollback":
        return rollback(root)
    print(__doc__)
    return 64


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
