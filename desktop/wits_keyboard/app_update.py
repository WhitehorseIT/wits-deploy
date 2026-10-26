"""Install a newer signed Linux build beside the running one, then restart into it.

The running copy is never modified. The new version is downloaded, checked against the signed
manifest, unpacked next to the current install and started by a small wrapper that falls back to
the previous version if the new one fails to start. The new version re-points the menu shortcut
only after it has been running for a while.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from . import __version__
from .online_release import SignedRelease, _open
from .release_check import parse_version
from .runtime import app_directory, data_directory, frozen
from .signing import SignatureError, check_file

ASSET = "linux-x86_64"
STATE_NAME = "app-update.json"
MAX_MEMBERS, MAX_UNPACKED = 20_000, 3 << 30
RESTART_SCRIPT = r'''new="$1"; old="$2"; delay="$3"; grace="$4"; state="$5"
sleep "$delay"
start=$(date +%s)
"$new/WITS-Deploy"
code=$?
if [ "$code" -ne 0 ] && [ $(( $(date +%s) - start )) -lt "$grace" ]; then
  rm -f "$state"
  exec "$old/WITS-Deploy"
fi
exit "$code"
'''


def unavailable_reason(release: SignedRelease | None) -> str | None:
    """Why this install cannot update itself (None when it can)."""
    if sys.platform != "linux" or not frozen():
        return "Self-update is available for the packaged Linux build; update source installs from the repository."
    if release is None or ASSET not in release.assets:
        return "No verified update is available."
    if not (parse_version(release.version) and parse_version(release.version) > parse_version(__version__)):
        return "This is already the newest version."
    parent = app_directory().parent
    if not os.access(parent, os.W_OK) or not (app_directory() / "WITS-Deploy").is_file():
        return f"The folder {parent} is not writable, so the app cannot install an update beside itself."
    return None


def _target_name(version: str) -> str:
    return f"WITS-Deploy-{version}-Linux-x86_64"


def state_path(directory: Path | None = None) -> Path:
    return (directory or data_directory()) / STATE_NAME


def download_app(release: SignedRelease, progress=None, cancelled=None, urlopen=urllib.request.urlopen,
                 parent: Path | None = None, directory: Path | None = None) -> Path:
    """Download, verify and unpack the signed Linux build next to the running one; returns its folder."""
    entry = release.assets[ASSET]
    parent = parent or app_directory().parent
    final = parent / _target_name(release.version)
    if (final / "WITS-Deploy").is_file():
        return final  # an earlier attempt finished unpacking; nothing is renamed until it is complete
    if final.exists():
        raise SignatureError(f"{final} exists but is not a complete install; remove it and try again")
    scratch = (directory or data_directory()) / "downloads"
    scratch.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".app-", dir=scratch))
    staging = Path(tempfile.mkdtemp(prefix=".WITS-Deploy-update-", dir=parent))
    try:
        archive, received = work / "app.tar.gz", 0
        with _open(release.asset_url(ASSET), 30.0, urlopen) as response, archive.open("wb") as out:
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
        _unpack(archive, staging, _target_name(release.version))
        unpacked = staging / _target_name(release.version)
        os.replace(unpacked, final)
        return final
    finally:
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)


def _unpack(archive: Path, destination: Path, top: str) -> None:
    if not hasattr(tarfile, "data_filter"):
        raise SignatureError("This Python cannot unpack archives safely")
    with tarfile.open(archive, "r:gz") as bundle:
        total = count = 0
        for member in bundle:
            count += 1
            total += max(member.size, 0)
            parts = Path(member.name).parts
            if count > MAX_MEMBERS or total > MAX_UNPACKED:
                raise SignatureError("The archive is too large")
            if not parts or parts[0] != top or member.isdev() or member.isfifo():
                raise SignatureError("The archive does not have the expected layout")
        try:
            bundle.extractall(destination, filter="data")  # also refuses unsafe links and absolute paths
        except tarfile.TarError as error:
            raise SignatureError(f"The archive contains an unsafe entry: {error}") from error
    if not (destination / top / "WITS-Deploy").is_file():
        raise SignatureError("The archive does not contain the application")


def write_pending(old: Path, new: Path, directory: Path | None = None) -> None:
    path = state_path(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"from": str(old), "to": str(new), "version": __version__}), encoding="utf-8")


def read_pending(directory: Path | None = None) -> dict | None:
    try:
        data = json.loads(state_path(directory).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and isinstance(data.get("to"), str) else None
    except (OSError, ValueError):
        return None


def restart_command(new: Path, old: Path, delay: float = 2, grace: float = 25, directory: Path | None = None):
    return ["/bin/sh", "-c", RESTART_SCRIPT, "wits-restart", str(new), str(old), str(delay), str(grace),
            str(state_path(directory))]


def restart(new: Path, directory: Path | None = None) -> None:
    """Start the new version shortly (after this one has released Bluetooth); the caller then quits."""
    old = app_directory()
    write_pending(old, new, directory)
    subprocess.Popen(restart_command(new, old, directory=directory), start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def confirm_started(directory: Path | None = None, refresh=None) -> str | None:
    """Called once the new version has been running a while: move the shortcuts over and clear the marker."""
    pending = read_pending(directory)
    if pending is None or Path(pending["to"]).resolve() != app_directory().resolve():
        return None
    if refresh is None:
        from .launcher import refresh_existing as refresh
    try:
        refresh()
    finally:
        state_path(directory).unlink(missing_ok=True)
    return pending.get("from")
