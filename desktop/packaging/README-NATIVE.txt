WITS DEPLOY @VERSION@ — STANDALONE DESKTOP PACKAGE

Extract the ENTIRE archive to a permanent folder. Keep the executable,
_internal and helpers folders together. No Python installation or pip setup
is required on the receiving machine. Firmware for all three boards is included.
OTA Update and USB Flash/Update preselect it; a newer external release can
still be chosen. USB requires the physical model/port; OTA reads the model.

Windows x64: double-click WITS-Deploy.exe. INSTALL-SHORTCUT.cmd adds a Start
menu shortcut. Running that command with --autostart instead creates a sign-in
shortcut. Remove WITS Deploy from your user's Startup folder to undo it.

Linux x86-64: extract the tar.gz, then launch WITS-Deploy. From its folder,
bash INSTALL-LAUNCHER.sh adds an app-menu shortcut. Add --autostart to also
launch after graphical sign-in, or --remove-autostart to disable sign-in
launch. Keep the extracted folder in place; reinstall the shortcut after moving.
The CI Linux package is built on Ubuntu 22.04; local builds inherit their host's
glibc requirements. System Bluetooth/BlueZ, Qt platform libraries and serial
port permissions remain OS requirements. No service or permission settings
are automatically changed.

All saved device aliases/settings retain their existing user settings identity.
Target checkboxes start unchecked. Starting automatically never arms boards
or sends text. Pair and connect using the usual workflow. Windows PIN entry
uses Bluetooth Settings; Linux uses the app dialog. USB Flash/Update includes
its esptool helper and supports blank boards; choose the exact physical model.

Logs: Windows %LOCALAPPDATA%\Whitehorse IT Solutions\WITS Deploy\logs;
Linux ${XDG_STATE_HOME:-~/.local/state}/wits-deploy/logs.
The app also displays the exact log path. PINs and typed payloads are omitted.

These first native packages are testing candidates. Build checks verify offline
Qt/backend imports and the bundled USB helper; they do not test a real Bluetooth
connection or physical flashing. Test those on Windows and Linux before wider
deployment. BUILD-INFO.json records the host and smoke-test result; SHA256SUMS.txt
and the archive's .sha256 file identify the contents. DEPENDENCIES.json records
third-party versions/license metadata. Retain it with the package.
