"""Update a run-from-source install (how Windows runs the app) from a signed source archive.

The app downloads and verifies the archive, unpacks the ``desktop`` folder into ``.update/staged`` and exits
with code 75. WINDOWS-START.cmd, which started the app, then runs ``apply_update.py`` to swap the files in
(nothing is in use at that point) and starts the app again. If the new version fails before it confirms itself,
the launcher restores the previous files.
"""
from __future__ import annotations

import json
import os
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from . import __version__, build_id
from .online_release import SignedRelease, _open
from .release_check import parse_version
from .runtime import app_directory, frozen
from .signing import SignatureError, check_file

UPDATE_EXIT_CODE = 75
LAUNCHER_ENV = "WITS_DEPLOY_LAUNCHER"
LAUNCHER_NAME = "windows-cmd"
MAX_MEMBERS, MAX_UNPACKED = 20_000, 1 << 30
MIN_FILES = ("wits_keyboard/__init__.py", "run.py", "requirements-release.txt")


@dataclass(frozen=True)
class Choice:
    """The update the dialog will offer."""
    release: SignedRelease
    label: str          # "release" or "snapshot"
    summary: str


def unavailable_reason(root: Path | None = None) -> str | None:
    """Why this install cannot update itself in place (None when it can)."""
    if frozen():
        return "This is the packaged build; use Update app… instead."
    if os.environ.get(LAUNCHER_ENV) != LAUNCHER_NAME:
        return "Start the app with WINDOWS-START.cmd to enable updating from inside the app."
    root = root or app_directory()
    if not (root / "apply_update.py").is_file():
        return "The update helper (apply_update.py) is missing; download a fresh copy of the app once."
    if not os.access(root, os.W_OK):
        return f"The folder {root} is not writable, so the app cannot update itself."
    return None


def choose(release, snapshot, include_snapshots: bool, current_version: str = __version__,
           current_build: str = "") -> Choice | None:
    """Pick the update to offer from the newest signed release and (optionally) the newest snapshot."""
    if include_snapshots and snapshot is not None and "source" in snapshot.assets:
        same = bool(current_build) and (snapshot.commit or "").startswith(current_build[:7])
        if not same:
            return Choice(snapshot, "snapshot",
                          f"development snapshot {snapshot.commit[:7]} (latest commit on main)")
    if (release is not None and "source" in release.assets and parse_version(release.version)
            and parse_version(release.version) > (parse_version(current_version) or (0,))):
        return Choice(release, "release", f"release {release.version}")
    return None


def _extract_desktop(archive: Path, staged: Path) -> None:
    """Unpack only the ``desktop`` folder of the archive (its single top-level folder is dropped)."""
    staged.mkdir(parents=True)
    total = count = 0
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        tops = {PurePosixPath(m.filename).parts[0] for m in members if PurePosixPath(m.filename).parts}
        if len(members) > MAX_MEMBERS or len(tops) != 1:
            raise SignatureError("The source archive does not have the expected layout")
        for member in members:
            name = PurePosixPath(member.filename)
            if name.is_absolute() or ".." in name.parts or "\\" in member.filename or ":" in member.filename:
                raise SignatureError("The source archive contains an unsafe path")
            parts = name.parts[1:]  # drop the top-level folder
            if len(parts) < 2 or parts[0] != "desktop" or member.is_dir():
                continue
            relative = parts[1:]
            if relative[0] in (".venv", "logs", ".update"):
                continue
            count += 1
            total += member.file_size
            if count > MAX_MEMBERS or total > MAX_UNPACKED:
                raise SignatureError("The source archive is too large")
            destination = staged.joinpath(*relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(member) as source, destination.open("wb") as sink:
                shutil.copyfileobj(source, sink)
    for needed in MIN_FILES:
        if not (staged / needed).is_file():
            raise SignatureError(f"The source archive is missing {needed}")


def stage(choice: Choice, progress=None, cancelled=None, urlopen=urllib.request.urlopen,
          root: Path | None = None) -> dict:
    """Download, verify and unpack the update into ``.update/staged`` and record it as pending."""
    release = choice.release
    entry = release.assets["source"]
    root = root or app_directory()
    update = root / ".update"
    shutil.rmtree(update / "staged", ignore_errors=True)
    update.mkdir(exist_ok=True)
    archive = update / "download.zip"
    try:
        received = 0
        with _open(release.asset_url("source"), 30.0, urlopen) as response, archive.open("wb") as out:
            for block in iter(lambda: response.read(1 << 16), b""):
                if cancelled is not None and cancelled.is_set():
                    raise InterruptedError("Update canceled")
                received += len(block)
                if received > entry["size"]:
                    raise SignatureError("The download is larger than the signed size")
                out.write(block)
                if progress:
                    progress(received, entry["size"])
        check_file(archive, entry)
        _extract_desktop(archive, update / "staged")
    except BaseException:
        shutil.rmtree(update / "staged", ignore_errors=True)
        raise
    finally:
        archive.unlink(missing_ok=True)
    info = {"version": release.version, "commit": release.commit or "", "channel": choice.label}
    (update / "pending.json").write_text(json.dumps(info), encoding="utf-8")
    return info


def confirm_started(root: Path | None = None) -> str | None:
    """After a healthy start: stop the launcher from rolling back, and drop the saved previous version.
    Returns a note for the event log, or None when no update was waiting for confirmation."""
    root = root or app_directory()
    update = root / ".update"
    if not (update / "unconfirmed").is_file():
        return None
    note = None
    try:
        applied = json.loads((update / "applied.json").read_text(encoding="utf-8"))
        note = f"Updated to {applied.get('version', '?')} {str(applied.get('commit') or '')[:7]}".strip()
    except (OSError, ValueError):
        note = "Updated"
    (update / "unconfirmed").unlink(missing_ok=True)
    shutil.rmtree(update / "previous", ignore_errors=True)
    return note


def rolled_back_note(root: Path | None = None) -> str | None:
    """If the launcher just restored the previous version, say so once."""
    marker = (root or app_directory()) / ".update" / "rolled-back"
    if marker.is_file():
        marker.unlink(missing_ok=True)
        return "The update did not start, so the previous version was restored."
    return None
