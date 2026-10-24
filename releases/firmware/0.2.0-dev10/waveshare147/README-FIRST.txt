WITS DEPLOY 0.2.0-dev10 — WAVESHARE 1.47 TOUCH BRING-UP

For ESP32-S3-Touch-LCD-1.47 only: 16MB flash, 8MB OPI PSRAM,
JD9853 LCD and AXS5106L touch. This is the first hardware test build.
Do not use this image on the non-touch S3 LCD, C6, T-QT Pro or 7-inch board.

Use its single USB-C connector. Hold BOOT, press/release RESET, release BOOT
to enter bootloader mode if it is not already there. Close serial monitors.

From the project root:
  .venv-pio/bin/python scripts/flash-waveshare147.py /dev/ttyACM0

Replace the port as necessary. It verifies hashes, requires an ESP32-S3 with
16MB flash, writes the factory image and verifies it. Factory installation
clears existing settings. Press RESET after SUCCESS. Expect PROGRAM and
version 0.2.0-dev10. Begin without a card to check the display and touch first.

Desktop app dev10 can also flash it: USB Flash/Update, Waveshare 1.47-inch
touch, correct port, common release JSON, Install blank board/factory recovery.
Windows standalone factory fallback from this folder:
  flash-windows.cmd COM5 WITS-Keyboard-Waveshare147-0.2.0-dev10.factory.bin

Hold HID for 2 seconds. In HID mode hold PAIR for 2 seconds, use the PIN on
screen, connect and Ping. Test ARM/sample text/STOP before adding storage.
CLEAR holds for 5 seconds; PROG holds for 2 seconds. Sliding off cancels.
BOOT is a fallback: hold for 2 seconds and RELEASE to enter HID or pair.

Storage starts read-only. Safely eject writable storage on the target PC
before remounting, switching mode, or updating. Use an expendable card for
the first storage tests. Do not format a drive merely because a host offers.

For subsequent updates use OTA Update or USB Flash/Update with the common
release manifest; do not assume app0 at 0x10000 is the selected slot after OTA.
USB --update in the helper preserves pairings and verifies the inactive slot.

Full hardware notes and test sequence: docs/boards/WAVESHARE147.md in source.
