#!/usr/bin/env python3
"""Fail if the documentation has drifted from the code. Run by the release workflow and the test suite.

Checks: the three version files agree; the current version has release notes; every relative link
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
    firmware = re.search(r'VERSION\[\] = "([^"]+)"', (ROOT / "src" / "firmware_version.h").read_text()).group(1)
    app = re.search(r'__version__ = "([^"]+)"', (ROOT / "desktop" / "wits_keyboard" / "__init__.py").read_text()).group(1)
    pointer = (ROOT / "desktop" / "packaging" / "firmware-release.txt").read_text().strip()
    return firmware, app, pointer


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
    if not firmware == app == pointer:
        found.append(f"Version files disagree: firmware {firmware}, app {app}, packaging pointer {pointer}")
    notes = ROOT / "docs" / "release-notes" / f"{firmware}.md"
    if not notes.is_file():
        found.append(f"Missing release notes: docs/release-notes/{firmware}.md")
    else:
        text = notes.read_text()
        if "## What's new" not in text or "## Files" not in text:
            found.append(f"{notes.relative_to(ROOT)} needs '## What's new' and '## Files' sections")
        if firmware not in text:
            found.append(f"{notes.relative_to(ROOT)} never mentions {firmware}")
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
