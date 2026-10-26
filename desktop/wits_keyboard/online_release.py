"""Find, verify and download signed releases from GitHub (nothing is trusted until its signature checks)."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from . import __version__
from .firmware_update import load_release
from .release_check import DISABLE_ENV, parse_version
from .release_keys import RELEASE_PUBLIC_KEYS
from .runtime import data_directory
from .signing import SignatureError, check_file, verify_manifest

DOWNLOAD_BASE = "https://github.com/WhitehorseIT/wits-deploy/releases/download"
RELEASES_URL = "https://api.github.com/repos/WhitehorseIT/wits-deploy/releases?per_page=50"
# The app and the firmware are released separately, each with its own tag prefix and signed manifest.
KINDS = {"app": "v", "firmware": "fw-v"}
SNAPSHOT_TAG = "snapshot"  # one rolling pre-release holding the signed source of the latest commit on main
MANIFEST_NAME, SIGNATURE_NAME = "release-manifest.json", "release-manifest.json.sig"
MAX_UNPACKED_BYTES, MAX_MEMBERS = 64 * 1024 * 1024, 200


@dataclass(frozen=True)
class SignedRelease:
    version: str
    critical_below: str | None
    assets: dict
    kind: str = "app"
    commit: str | None = None      # snapshots only: the commit the source archive was made from
    sequence: int | None = None    # snapshots only: increases with every published snapshot

    @property
    def tag(self) -> str:
        return SNAPSHOT_TAG if self.kind == "source" else KINDS[self.kind] + self.version

    def asset_url(self, label: str) -> str:
        return f"{DOWNLOAD_BASE}/{self.tag}/{self.assets[label]['name']}"


def _open(url: str, timeout: float, urlopen):
    request = urllib.request.Request(url, headers={"User-Agent": f"WITS-Deploy/{__version__}",
                                                   "Accept": "application/octet-stream, application/json"})
    return urlopen(request, timeout=timeout)


def _read(url: str, limit: int, urlopen, timeout: float = 8.0) -> bytes:
    with _open(url, timeout, urlopen) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise SignatureError("A downloaded file was larger than expected")
    return data


class TrustState:
    """Keys added by earlier signed releases and the newest version ever seen (blocks downgrades)."""

    def __init__(self, directory: Path | None = None):
        self.path = (directory or data_directory()) / "release-state.json"

    def load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def keys(self) -> tuple[str, ...]:
        extra = [key for key in self.load().get("keys", []) if isinstance(key, str)]
        return tuple(dict.fromkeys((*RELEASE_PUBLIC_KEYS, *extra)))

    def highest(self, kind: str = "app") -> str | None:
        state = self.load()
        table = state.get("highest") if isinstance(state.get("highest"), dict) else {}
        value = table.get(kind) or (state.get("highest_version") if kind == "app" else None)  # older state file
        return value if isinstance(value, str) and parse_version(value) else None

    def snapshot_sequence(self) -> int:
        value = self.load().get("snapshot_sequence")
        return value if type(value) is int and value >= 0 else 0

    def record_snapshot(self, sequence: int, added_keys=()) -> None:
        state = self.load()
        state["snapshot_sequence"] = max(self.snapshot_sequence(), sequence)
        state["keys"] = sorted({*state.get("keys", []), *added_keys})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def record(self, version: str, added_keys, kind: str = "app") -> None:
        state = self.load()
        highest = self.highest(kind)
        table = dict(state["highest"]) if isinstance(state.get("highest"), dict) else {}
        if highest is None or parse_version(version) > parse_version(highest):
            table[kind] = version
        state["highest"] = table
        state["keys"] = sorted({*state.get("keys", []), *added_keys})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)


def fetch_signed(version: str, urlopen=urllib.request.urlopen, state: TrustState | None = None,
                 kind: str = "app") -> SignedRelease:
    """Download and verify one release's manifest. Raises SignatureError (or OSError offline)."""
    state = state or TrustState()
    base = f"{DOWNLOAD_BASE}/{KINDS[kind]}{version}"
    manifest_bytes = _read(f"{base}/{MANIFEST_NAME}", 64 * 1024, urlopen)
    signature = _read(f"{base}/{SIGNATURE_NAME}", 1024, urlopen).decode("ascii", "replace")
    data = verify_manifest(manifest_bytes, signature, state.keys())
    if data["version"] != version:
        raise SignatureError("The signed manifest is for a different version")
    if data.get("kind", "app") != kind:  # manifests from before the split have no kind and are app releases
        raise SignatureError("The signed manifest is for a different kind of release")
    highest = state.highest(kind)
    if highest and parse_version(data["version"]) < parse_version(highest):
        raise SignatureError("Refusing an older release than one already seen (possible downgrade)")
    state.record(data["version"], data.get("add_keys", []), kind)
    return SignedRelease(data["version"], data.get("critical_below"), data["assets"], kind)


def fetch_snapshot(urlopen=urllib.request.urlopen, state: TrustState | None = None) -> SignedRelease:
    """Download and verify the newest source snapshot. Raises SignatureError (or OSError offline)."""
    state = state or TrustState()
    base = f"{DOWNLOAD_BASE}/{SNAPSHOT_TAG}"
    manifest_bytes = _read(f"{base}/{MANIFEST_NAME}", 64 * 1024, urlopen)
    signature = _read(f"{base}/{SIGNATURE_NAME}", 1024, urlopen).decode("ascii", "replace")
    data = verify_manifest(manifest_bytes, signature, state.keys())
    if data.get("kind") != "source" or "source" not in data["assets"]:
        raise SignatureError("The signed manifest is not a source snapshot")
    if data.get("sequence") is None or not data.get("commit"):
        raise SignatureError("The snapshot manifest lacks its commit or sequence")
    if data["sequence"] < state.snapshot_sequence():
        raise SignatureError("Refusing an older snapshot than one already seen (possible downgrade)")
    state.record_snapshot(data["sequence"], data.get("add_keys", []))
    return SignedRelease(data["version"], data.get("critical_below"), data["assets"], "source",
                         data["commit"], data["sequence"])


def fetch_listing(urlopen=urllib.request.urlopen) -> list[str] | None:
    """Tags of the published (non-draft) releases, or None when offline or opted out. One API request."""
    if os.environ.get(DISABLE_ENV):
        return None
    try:
        listing = json.loads(_read(RELEASES_URL, 2_000_000, urlopen))
    except Exception:
        return None
    if not isinstance(listing, list):
        return None
    return [str(r.get("tag_name", "")) for r in listing if isinstance(r, dict) and not r.get("draft")]


def latest_signed(urlopen=urllib.request.urlopen, state: TrustState | None = None,
                  kind: str = "app", tags: list[str] | None = None) -> SignedRelease | None:
    """The newest release of this kind whose manifest verifies, or None (offline, opted out, or nothing signed)."""
    if tags is None:
        tags = fetch_listing(urlopen)
    prefix = KINDS[kind]
    versions = sorted({t[len(prefix):] for t in tags or () if t.startswith(prefix) and parse_version(t[len(prefix):])},
                      key=parse_version, reverse=True)
    for version in versions[:3]:  # a newest release without a manifest falls back to the one before it
        try:
            return fetch_signed(version, urlopen, state, kind)
        except Exception:
            continue
    return None


def download_firmware(release: SignedRelease, progress=None, urlopen=urllib.request.urlopen,
                      directory: Path | None = None) -> Path:
    """Download the signed firmware bundle, verify it and unpack it; returns the .ota.json path."""
    entry = release.assets.get("firmware")
    if entry is None:
        raise SignatureError("This release has no firmware bundle")
    root = (directory or data_directory()) / "firmware"
    target = root / release.version
    finished = target / ".verified"
    if finished.is_file():
        manifests = sorted(target.glob("*.ota.json"))
        if manifests:
            return manifests[0]
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".download-", dir=root))
    try:
        archive = work / "bundle.zip"
        digest, received = hashlib.sha256(), 0
        with _open(release.asset_url("firmware"), 30.0, urlopen) as response, archive.open("wb") as out:
            for block in iter(lambda: response.read(1 << 16), b""):
                received += len(block)
                if received > entry["size"]:
                    raise SignatureError("The download is larger than the signed size")
                digest.update(block)
                out.write(block)
                if progress:
                    progress(received, entry["size"])
        check_file(archive, entry)
        unpacked = work / "unpacked"
        _extract(archive, unpacked)
        manifests = sorted(unpacked.glob("*.ota.json"))
        if len(manifests) != 1 or load_release(manifests[0]).version != release.version:
            raise SignatureError("The firmware bundle does not match the signed release")
        (unpacked / ".verified").write_text(release.version, encoding="utf-8")
        shutil.rmtree(target, ignore_errors=True)
        os.replace(unpacked, target)
        return next(target.glob("*.ota.json"))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    total = 0
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > MAX_MEMBERS:
            raise SignatureError("The firmware bundle has too many files")
        for member in members:
            name = PurePosixPath(member.filename)
            if (name.is_absolute() or ".." in name.parts or "\\" in member.filename
                    or ":" in member.filename or member.is_dir() and not member.filename.endswith("/")):
                raise SignatureError("The firmware bundle contains an unsafe path")
            total += member.file_size
            if total > MAX_UNPACKED_BYTES:
                raise SignatureError("The firmware bundle is too large when unpacked")
            if member.is_dir():
                continue
            out = destination.joinpath(*name.parts)
            out.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(member) as source, out.open("wb") as sink:
                shutil.copyfileobj(source, sink)
