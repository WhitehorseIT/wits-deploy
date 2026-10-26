"""Compare board firmware with the newest known release (notify only; nothing is downloaded)."""
from __future__ import annotations

import re
from dataclasses import dataclass

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


def newest_from_tags(tags, prefix: str) -> Latest | None:
    """The newest version among release tags that start with ``prefix`` ("v" for the app, "fw-v" for
    firmware). Tags of the other stream, and anything unparseable, are ignored."""
    versions = [t[len(prefix):] for t in tags if isinstance(t, str) and t.startswith(prefix)
                and parse_version(t[len(prefix):]) and (prefix != "v" or not t.startswith("fw-"))]
    return Latest(max(versions, key=parse_version)) if versions else None


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
