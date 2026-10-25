"""Compare board firmware with the newest known release (notify only; nothing is downloaded)."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass

from . import __version__

RELEASES_URL = "https://api.github.com/repos/WhitehorseIT/wits-deploy/releases?per_page=30"
DISABLE_ENV = "WITS_DEPLOY_NO_UPDATE_CHECK"
_STAGE = {"dev": 0, "rc": 1}

CURRENT, UPDATE, CRITICAL = "current", "update", "critical"


def parse_version(text: str) -> tuple | None:
    """0.2.0-dev18 < 0.2.0-rc1 < 0.2.0 < 0.2.1. Returns None when unparseable."""
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:-(dev|rc)(\d*))?", (text or "").strip())
    if not match:
        return None
    major, minor, patch, stage, number = match.groups()
    rank = (_STAGE[stage], int(number or 0)) if stage else (2, 0)
    return int(major), int(minor), int(patch), rank


@dataclass(frozen=True)
class Latest:
    version: str
    critical_below: str | None = None


def newest(*candidates: Latest | None) -> Latest | None:
    """The highest version, keeping the strictest critical threshold seen."""
    known = [c for c in candidates if c and parse_version(c.version)]
    if not known:
        return None
    best = max(known, key=lambda c: parse_version(c.version))
    floors = [c.critical_below for c in known if c.critical_below and parse_version(c.critical_below)]
    floor = max(floors, key=parse_version) if floors else None
    return Latest(best.version, floor)


def classify(board_version: str, latest: Latest | None) -> str | None:
    """CURRENT, UPDATE or CRITICAL; None when either side cannot be compared."""
    board, target = parse_version(board_version), parse_version(latest.version) if latest else None
    if board is None or target is None:
        return None
    if latest.critical_below and (floor := parse_version(latest.critical_below)) and board < floor:
        return CRITICAL
    return UPDATE if board < target else CURRENT


def from_release_json(data: dict) -> Latest | None:
    tag = str(data.get("tag_name") or "").strip().lstrip("v")
    if not parse_version(tag):
        return None
    return Latest(tag)  # release notes are not trusted for critical flags; see signing.py


def from_release_list(releases) -> Latest | None:
    """Newest published release, prereleases included (the project is still on test builds)."""
    if not isinstance(releases, list):
        return None
    return newest(*(from_release_json(r) for r in releases
                    if isinstance(r, dict) and not r.get("draft")))


def fetch_latest(url: str = RELEASES_URL, timeout: float = 6.0) -> Latest | None:
    """Ask GitHub for the newest published release. Sends no identifying data; None on any failure."""
    if os.environ.get(DISABLE_ENV):
        return None
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json", "User-Agent": f"WITS-Deploy/{__version__}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return from_release_list(json.loads(response.read(2_000_000)))
    except Exception:
        return None


def bundled_latest() -> Latest | None:
    """The firmware that ships with this app, usable offline."""
    try:
        from .firmware_bundle import bundled_manifest
        from .firmware_update import load_release
        path = bundled_manifest()
        if path:
            return Latest(load_release(path).version)
        from pathlib import Path
        pointer = Path(__file__).resolve().parents[1] / "packaging" / "firmware-release.txt"
        return Latest(pointer.read_text().strip()) if pointer.is_file() else None
    except Exception:
        return None
