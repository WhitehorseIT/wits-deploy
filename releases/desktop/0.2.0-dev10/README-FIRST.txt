WITS DEPLOY CONTROLLER 0.2.0-dev10
Whitehorse IT Solutions — October 24, 2026

WINDOWS
1. Close the previous app and extract this ZIP into a NEW writable folder.
2. Install 64-bit Python 3.11 or newer with the Python launcher (py).
3. In app, run SETUP-WINDOWS.cmd, then START-WINDOWS.cmd. Internet is needed
   for the first dependency installation. Keep the console open.

LINUX
From app run bash SETUP-LINUX.sh, then bash START-LINUX.sh. Bluetooth LE and
Python venv support are required. Existing user aliases/bonds remain available;
Target boxes always start unchecked. This ZIP is Python source, not an EXE.

CHANGES
Dev10 adds Waveshare ESP32-S3-Touch-LCD-1.47 firmware selection and 16MB USB
flashing. The new board is in hardware bring-up; display/touch, Bluetooth,
keyboard, storage and updates need physical testing. Original T-QT Pro and
Waveshare7 behavior is retained. Old keyboard-only firmware remains usable;
OTA requires OTA-capable firmware (dev8+ on old models, dev10+ on Waveshare147).
This app ZIP contains NO firmware. Obtain the separate dev10 firmware ZIP.

FIRST FLASH OF THE 1.47-INCH TOUCH BOARD
Use its single USB-C connector. Hold BOOT, press/release RESET, release BOOT
if needed. Close serial monitors. Click USB Flash/Update, select Waveshare
1.47-inch touch, the correct COM/serial port and the extracted firmware ZIP's
WITS-Keyboard-Release-0.2.0-dev10.ota.json. Preserve all its model subfolders.
Choose Install blank board / factory recovery. This clears existing settings.
The flasher requires ESP32-S3 and 16MB flash; always select the exact board.
Keep power connected, wait for verification and press RESET. Expect PROGRAM
and version 0.2.0-dev10. First test without an SD card. Hold HID for 2 seconds.

PAIR AND TEST
Hold PAIR for 2 seconds; enter the six-digit PIN shown on the screen. Linux
uses the app's PIN dialog. Windows uses Bluetooth Settings for initial PIN
pairing, then Connect in the app. Saved bonds normally reconnect directly.
Use Re-pair only for a stale bond/service cache after opening physical PAIR.
Ping displays an acknowledgment and timing. Identify displays the row alias.
Select only intended Target boxes and physically ARM before sending. Test a
sample with Before sending set to 5 seconds, then focus a text editor. Between
characters is a separate setting. STOP ALL is immediate. Do not use real
credentials during bring-up. CLEAR holds 5 seconds; PROG holds 2 seconds.

STORAGE
Supported Waveshare models export MicroSD over USB; default is read-only.
Safely eject writable storage on its target PC before remounting, resetting
or updating. Use an expendable card for initial read/write checks. T-QT Pro
has no MicroSD support. The 7-inch board has separate UART and USB connectors;
the 1.47-inch board uses its single USB-C connector for programming and HID/MSC.

UPDATES
OTA Update reads the connected model and selects its matching app image from
the common JSON. Keep the release folders intact. The paired BLE connection
carries data; your PC stays online. Disarm first and safely eject storage.
The app shows speed/ETA and acknowledgment progress. Verified success reboots
the board into PROGRAM. Enter HID and reconnect. Windows initial pairing
remains an OS operation. A one-time Linux Re-pair may refresh pre-OTA caches.

USB Flash/Update can install a blank board or update an existing WITS board.
Update working board checks the existing partition table, writes/verifies the
inactive slot, then commits the other OTA metadata sector. Pairings remain.
Factory recovery writes the complete image and clears board settings. Do not
manually assume app0 at 0x10000 is selected after OTA. Keep USB connected until
verification finishes and press RESET afterward.

DIAGNOSTICS AND LIMITS
Debug output goes to app/logs/wits-keyboard-debug.log, rotating at 4MiB.
Typed content and PINs are omitted. Send the log, exact action and approximate
time after failures. No existing logs, settings or credentials are packaged.
Automated tests cover protocol, pairing, delays, targeting, storage status,
firmware selection, Bluetooth transfers and USB update planning. They use
simulated devices. New-board hardware, serial flashing and interrupted-update
recovery require physical tests; previous full OTA uploads passed on the two
original models. MANIFEST.json/SHA256SUMS.txt and the companion .zip.sha256
identify the packaged files.
