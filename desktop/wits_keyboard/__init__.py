"""Native controller for WITS Deployment Keyboard devices."""

__version__ = "0.2.0-dev24"


def build_id() -> str:
    """Short commit id of this copy of the code, or an empty string when it is not known (packaged builds)."""
    from ._build import COMMIT
    if COMMIT and not COMMIT.startswith("$"):
        return COMMIT
    try:
        import subprocess
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        if (root / ".git").exists():
            result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True,
                                    text=True, timeout=5)
            return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        pass
    return ""


def version_label() -> str:
    """The version, with the build id when it is known: 0.2.0-dev24 (build 87c1e18)."""
    build = build_id()
    return f"{__version__} (build {build})" if build else __version__
