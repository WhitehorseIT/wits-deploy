WITS KEYBOARD 0.1.0 - STABLE RELEASE
Whitehorse IT Solutions - October 23, 2026

This bundle contains the Python desktop controller for Windows/Linux and
firmware for the LILYGO T-QT Pro ESP32-S3 (4 MB flash, 2 MB PSRAM).

  app\       Controller source, dependencies, setup/launch scripts and tests
  firmware\  App-only/factory images and flashing instructions

FIRMWARE IS IDENTICAL TO TESTED rc13. If your board already runs rc13,
there is no need to flash again. The stable filenames/version label changed;
the firmware bytes did not. Install/run the included app for its versioned UI.

APP SETUP

Requires 64-bit Python 3.11 or newer, Bluetooth LE, and internet for the first
dependency install. This release is a Python source application, not a
standalone EXE. The setup scripts use pinned direct dependencies.

Windows:
  Install Python from https://www.python.org/downloads/windows/ and include
  the Python launcher. Extract the entire ZIP to a writable folder. In app,
  double-click SETUP-WINDOWS.cmd, then START-WINDOWS.cmd.

Linux:
  Extract the ZIP, open a terminal in app, and run:
    bash SETUP-LINUX.sh
    bash START-LINUX.sh
  Bluetooth must be powered on and your distribution's Python venv support
  must be installed. Existing source checkouts can continue using their
  .venv/bin/python run.py command.

CONNECT AND USE

1. After resetting the board, hold the right/HID button for two seconds to
   enter HID mode. A bonded computer can then Connect without holding left.
2. On a first pairing, hold left for two seconds to display a fresh PIN.
   Linux: select the board and Connect in the app; enter its PIN when asked.
   Windows: pair in Windows Bluetooth Settings first, then Connect in the app.
   To replace a stale Windows bond, remove that board in Windows Settings and
   pair there again; the app's Windows in-app PIN workflow is not supported.
3. Scan if necessary, highlight the board row, and Connect. Ping shows the
   acknowledgement and round-trip time. Device rows/aliases are remembered.
4. Check explicit Target boxes for sending. Physically arm each destination
   using its right button; the app shows live ARMED/DISARMED/TYPING badges.
5. Set Before sending (seconds) and Between characters (milliseconds)
   independently. Defaults are 0 seconds and 25 ms. A delayed send can be
   canceled, and STOP ALL remains immediate.
6. Send text or special keys to the board's USB target. For a same-computer
   test, use a start delay so you can focus Notepad/an editor before typing.

Left short press stops; right short press arms/disarms. Right held five
seconds clears saved board bonds. Pairings and local aliases survive app
restarts. Rename is local to the controller; Identify displays that alias with
the permanent hardware ID underneath. The BLE broadcast name stays fixed.

UPDATE AN ALREADY-WORKING BOARD WHILE PRESERVING ITS BONDS

Use WITS-Keyboard-0.1.0.app.bin at flash address 0x10000. Factory images write
from 0x0 and can overwrite stored bonds; reserve them for initial setup or
recovery. App-only updates require the existing 4 MB partition layout.

Enter bootloader mode: hold left/BOOT while pressing RESET, then release
left. Alternatively hold left/FLASH on the blue programming screen.

Windows, from the firmware folder (replace COM5 as appropriate):
  py -m pip install esptool
  .\flash-windows.cmd COM5 .\WITS-Keyboard-0.1.0.app.bin

Linux, from the firmware folder (replace the serial port as appropriate):
  python3 -m esptool --chip esp32s3 --port /dev/ttyACM0 --baud 460800 write-flash 0x10000 WITS-Keyboard-0.1.0.app.bin

Press RESET manually after flashing, then enter HID mode using right/HID.

DIAGNOSTICS AND RELEASE DETAILS

Logs are in app/logs/wits-keyboard-debug.log, created on launch. Typed payload
content is omitted. The archive includes no existing logs, secrets or pairings.
See app/README.md for detailed behavior and RELEASE-NOTES.md for coverage.
MANIFEST.json and SHA256SUMS.txt identify the packaged files; firmware also
has its own checksums. The distribution ZIP has a companion .sha256 file.
