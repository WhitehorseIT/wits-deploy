WITS KEYBOARD CONTROLLER 0.2.0-dev7 - TESTER'S APP UPDATE
Whitehorse IT Solutions - October 23, 2026

This ZIP contains the updated Python desktop application, setup/start scripts,
pinned dependencies and tests. It contains NO firmware. Keep the T-QT Pro
0.1.1.app.bin firmware Whitehorse IT Solutions already sent; no extra flash is needed for this
app update. The Waveshare touchscreen firmware is a separate hardware build.

WINDOWS SETUP

1. Close the previous WITS Keyboard app.
2. Extract the entire ZIP into a NEW writable folder (not inside the ZIP).
3. Install 64-bit Python 3.11 or newer if necessary:
   https://www.python.org/downloads/windows/
   Include the Python launcher (the "py" command).
4. Open the app folder and double-click SETUP-WINDOWS.cmd.
   Internet is required for its first dependency installation.
5. Double-click START-WINDOWS.cmd. Keep its console open while using the app.

This is a Python application, not a standalone EXE. Setup creates its own
local .venv and does not reuse the old bundle's environment. Device aliases
and saved device rows use the existing Windows user settings; target boxes
start unchecked. Bluetooth bonds remain managed by Windows/the board.

CONNECT AND TEST YOUR T-QT PRO

1. After RESET, hold the right/HID button for 2 seconds.
2. For an existing bond, highlight your saved board and Connect.
3. On first pairing, hold left/PAIR for 2 seconds. Pair in Windows Bluetooth
   Settings first, entering the PIN displayed on the board, then Connect in
   the app. Windows PIN pairing remains handled by Windows Settings.
4. Ping should show acknowledgment and time. Use Identify to locate a board.
5. Check the board's Target box and physically ARM with its right button.
6. For a same-PC typing test, set Before sending to 5 seconds, send a sample
   string, then focus Notepad. Between characters is a separate millisecond
   delay (default 25). STOP ALL stays immediate.

CHANGES IN THIS APP

- Storage status and per-board read-only/read-write mount controls for the
  new Waveshare MicroSD model. A supported board must be disarmed, and its
  USB drive safely ejected from the target PC, before changing access mode.
- Verifies remount/access state before announcing success; reports late host
  ejects or revoked permissions instead of incorrectly reporting a mount.
- Keeps existing multi-device targeting, ARM/DISARMED status, Ping feedback,
  remembered devices/aliases, Identify labels and independent send delays.

T-QT Pro 0.1.1 does not provide SD storage or the newer storage-information
characteristic. Keyboard operation remains compatible; storage mode buttons
stay unavailable for that board. An optional information lookup failure in
the debug log does not mean that keyboard connection failed.

FEEDBACK / DIAGNOSTICS

Please test connect/reconnect, Ping, ARM/DISARM, sample text, special keys,
both delay controls and STOP. Mention any UI/readability issues in dark mode.
After a failure, send Whitehorse IT Solutions app/logs/wits-keyboard-debug.log (and rotated
copies if present), together with what you clicked and the approximate time.
The package includes no existing logs, credentials, local settings or bonds.
Typed text contents are omitted from application debug logging.

Linux users can run bash SETUP-LINUX.sh and bash START-LINUX.sh from app.
Python venv support and Bluetooth LE must be available. Linux in-app PIN
pairing is supported; Windows uses the OS pairing flow described above.

Verification: automated tests cover legacy keyboard connection when storage
information is absent, wire protocol, targeting, delay/cancel behavior,
pairing and storage remount feedback. Windows runtime verification of this
specific snapshot awaits the tester; previous Windows releases worked on the tester's PC.

MANIFEST.json and SHA256SUMS.txt identify all packaged files. A companion
.zip.sha256 file verifies the archive.

HOTSPOT UPDATER IN THIS SNAPSHOT

The Update firmware button supports the 7-inch Waveshare with dev7 or newer
OTA-capable firmware. Join its physically enabled WITS-Update hotspot through
the OS Wi-Fi menu, then select the .ota.json beside its .app.bin and enter
the current on-screen password. This feature is not available on your T-QT
Pro 0.1.1 firmware yet; your existing keyboard functions remain compatible.
The 7-inch board requires one initial serial update before OTA is available.

All 82 desktop tests pass. Hotspot upload has not yet been tested on real
Windows hardware; first hardware verification is still pending on Linux too.
