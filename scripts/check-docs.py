#!/usr/bin/env python3
"""Fail if the documentation has drifted from the code. Run by the release workflow and the test suite.

Checks: the version files are valid and consistent; the app and firmware versions each have release notes; every relative link
and heading anchor in the Markdown files resolves; every guide under docs/ is reachable from the
README; the retired product name appears only where the naming guide explains it.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN = [ROOT / "README.md", ROOT / "SECURITY.md", ROOT / "desktop" / "README.md",
            ROOT / "releases" / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
OLD_NAME_ALLOWED = {"docs/DEVELOPMENT.md", "releases/README.md"}  # both explain legacy file names


def versions():
    """(firmware source version, app version, firmware version the app bundles)."""
    firmware = re.search(r'VERSION\[\] = "([^"]+)"', (ROOT / "src" / "firmware_version.h").read_text()).group(1)
    app = re.search(r'__version__ = "([^"]+)"', (ROOT / "desktop" / "wits_keyboard" / "__init__.py").read_text()).group(1)
    pointer = (ROOT / "desktop" / "packaging" / "firmware-release.txt").read_text().strip()
    return firmware, app, pointer


def version_key(text: str):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-(dev|rc)(\d*))?", text)
    if not match:
        return None
    major, minor, patch, stage, number = match.groups()
    return int(major), int(minor), int(patch), ({"dev": 0, "rc": 1}[stage], int(number or 0)) if stage else (2, 0)


def slug(heading: str) -> str:
    text = re.sub(r"[`*_]", "", heading.strip().lower())
    return re.sub(r"\s", "-", re.sub(r"[^\w\s-]", "", text))


def anchors(path: Path) -> set[str]:
    found, in_code = set(), False
    for line in path.read_text().splitlines():
        if line.startswith("```"):
            in_code = not in_code
        elif not in_code and (match := re.match(r"#{1,6}\s+(.*)", line)):
            found.add(slug(match.group(1)))
    return found


def problems() -> list[str]:
    found = []
    firmware, app, pointer = versions()
    notes_dir = ROOT / "docs" / "release-notes"
    for label, value in (("firmware", firmware), ("app", app), ("bundled firmware", pointer)):
        if version_key(value) is None:
            found.append(f"The {label} version {value!r} is not a valid version")
    if version_key(pointer) and version_key(firmware) and version_key(pointer) > version_key(firmware):
        found.append(f"The app bundles firmware {pointer}, newer than the firmware source ({firmware})")
    wanted = [(f"{app}.md", app, "app")]
    for version in dict.fromkeys((firmware, pointer)):
        # releases before the app/firmware split had one combined notes file named after the version
        name = next((n for n in (f"firmware-{version}.md", f"{version}.md") if (notes_dir / n).is_file()),
                    f"firmware-{version}.md")
        wanted.append((name, version, "firmware"))
    for name, version, label in wanted:
        notes = notes_dir / name
        if not notes.is_file():
            found.append(f"Missing release notes: docs/release-notes/{name}")
            continue
        text = notes.read_text()
        if "## What's new" not in text or "## Files" not in text:
            found.append(f"{notes.relative_to(ROOT)} needs '## What's new' and '## Files' sections")
        if version not in text:
            found.append(f"{notes.relative_to(ROOT)} never mentions {version}")
    linked = set()
    for md in MARKDOWN:
        rel = md.relative_to(ROOT).as_posix()
        text = md.read_text()
        prose = re.sub(r"```.*?```", "", text, flags=re.S)
        for target, fragment in re.findall(r"\]\(([^)#\s]*)(#[^)\s]*)?\)", prose):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            destination = (md.parent / target).resolve() if target else md
            if not destination.exists():
                found.append(f"{rel}: broken link {target}")
                continue
            linked.add(destination)
            if fragment and destination.suffix == ".md" and fragment[1:] not in anchors(destination):
                found.append(f"{rel}: no heading for anchor {target}{fragment}")
        if rel not in OLD_NAME_ALLOWED and not rel.startswith("docs/release-notes/") \
                and re.search(r"WITS Keyboard|WITS-Keyboard", prose):
            found.append(f"{rel}: mentions the old product name")
    for guide in sorted((ROOT / "docs").glob("*.md")) + sorted((ROOT / "docs" / "boards").glob("*.md")):
        if guide.resolve() not in linked:
            found.append(f"{guide.relative_to(ROOT)} is not linked from any other document")
    return found


def main() -> int:
    found = problems()
    for item in found:
        print("docs:", item, file=sys.stderr)
    if not found:
        print("Documentation checks passed.")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
