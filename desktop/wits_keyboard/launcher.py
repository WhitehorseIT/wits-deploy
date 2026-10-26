"""Install a per-user Linux menu shortcut, optionally also at sign-in."""
import argparse
import os
from pathlib import Path
import sys
from .runtime import DESKTOP_ID, app_directory, frozen

FILENAME = DESKTOP_ID + ".desktop"


def quote_argument(value):
    if any(char in value for char in "\n\r\0"):
        raise ValueError("Launcher paths cannot contain line breaks or NUL")
    # Exec arguments are not shell commands. Escape the Exec quoting layer,
    # then the desktop-entry string layer (freedesktop Desktop Entry spec).
    escaped = "".join("\\" + c if c in '\\"`$' else c for c in value)
    return '"' + escaped.replace("\\", "\\\\").replace("%", "%%") + '"'


def desktop_entry():
    root = app_directory()
    command = [str(root / "WITS-Deploy")] if frozen() else ["/bin/bash", str(root / "START-LINUX.sh")]
    return ("[Desktop Entry]\nType=Application\nName=WITS Deploy\n"
            "Comment=Whitehorse IT deployment controller\n"
            "Exec=" + " ".join(quote_argument(arg) for arg in command) + "\n"
            "Icon=input-keyboard\nTerminal=false\nCategories=Utility;\n"
            "StartupNotify=true\n")


def refresh_existing():
    """Point the menu and sign-in shortcuts that already exist at this install. Returns the files updated."""
    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    entry, updated = desktop_entry(), []
    for path in (data / "applications" / FILENAME, config / "autostart" / FILENAME):
        if path.is_file():
            path.write_text(entry, encoding="utf-8")
            path.chmod(0o755)
            updated.append(path)
    return updated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write a shortcut here instead of installing in the app menu")
    parser.add_argument("--autostart", action="store_true", help="also start the app after graphical sign-in")
    parser.add_argument("--remove-autostart", action="store_true", help="remove this app's sign-in shortcut")
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("this installer is for Linux")
    if args.autostart and args.remove_autostart:
        parser.error("choose either --autostart or --remove-autostart")
    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    menu = args.output or data / "applications" / FILENAME
    entry = desktop_entry()
    menu.parent.mkdir(parents=True, exist_ok=True)
    menu.write_text(entry, encoding="utf-8")
    menu.chmod(0o755)
    print(f"Shortcut: {menu}")
    startup = config / "autostart" / FILENAME
    if args.autostart:
        startup.parent.mkdir(parents=True, exist_ok=True)
        startup.write_text(entry, encoding="utf-8")
        print(f"Start at sign-in: {startup}")
    elif args.remove_autostart:
        startup.unlink(missing_ok=True)
        print("WITS Deploy sign-in shortcut removed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
