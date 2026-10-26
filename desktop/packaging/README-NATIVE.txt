WITS DEPLOY @VERSION@ — STANDALONE DESKTOP PACKAGE

Extract the ENTIRE archive to a permanent folder. Keep the executable,
_internal and helpers folders together. No Python installation or pip setup
is required on the receiving machine. Firmware for all three boards is included.
OTA Update and USB Flash/Update preselect it; a newer release can be downloaded
from OTA Update, or another release JSON can be chosen. USB flashing needs the
physical model and port; OTA reads the model from the connected board.

Windows x64 (testing package): double-click WITS-Deploy.exe. INSTALL-SHORTCUT.cmd
adds a Start menu shortcut. Running that command with --autostart instead
creates a sign-in shortcut. Remove WITS Deploy from your user's Startup folder
to undo it. Unsigned executables may trigger SmartScreen warnings.

Linux x86-64: extract the tar.gz, then launch WITS-Deploy. From its folder,
bash INSTALL-LAUNCHER.sh adds an app-menu shortcut. Add --autostart to also
launch after graphical sign-in, or --remove-autostart to disable sign-in
launch. Keep the extracted folder in place; reinstall the shortcut after moving.
The CI Linux package is built on Ubuntu 22.04; local builds inherit their host's
glibc requirements. System Bluetooth/BlueZ, Qt platform libraries and serial
port permissions remain OS requirements. No service or permission settings
are automatically changed.

Updates (Linux): when a newer signed release exists, Update app... appears in
the app. It downloads and verifies the new version, installs it beside this one
and restarts into it; this copy stays as a fallback until you delete it.

Saved device names and settings carry over between versions. Target checkboxes
start unchecked. Starting automatically never arms boards or sends text. Pair
and connect using the usual workflow: Linux uses the app's PIN dialog, Windows
pairs through Bluetooth Settings first. Each board has an Auto-connect box that
reconnects it using the existing OS pairing; first pairing stays manual, and a
manual Disconnect pauses it until Connect, a toggle, or an app restart.

Safely eject writable USB storage on its host before changing mode, resetting
or updating a board. A read/write grant stays in place if the app closes or
Bluetooth drops, so the computer's cached writes are never cut off.

Logs: Windows %LOCALAPPDATA%\Whitehorse IT Solutions\WITS Deploy\logs;
Linux ${XDG_STATE_HOME:-~/.local/state}/wits-deploy/logs.
The app also displays the exact log path. PINs and typed payloads are omitted.

These are testing builds. Build checks verify offline Qt/backend imports and
the bundled USB helper; they do not test a real Bluetooth connection or physical
flashing. BUILD-INFO.json records the host and smoke-test result; SHA256SUMS.txt
and the archive's .sha256 file identify the contents. DEPENDENCIES.json records
third-party versions and license metadata. Retain it with the package.
