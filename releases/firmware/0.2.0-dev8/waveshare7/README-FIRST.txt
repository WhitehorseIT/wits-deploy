WITS KEYBOARD 0.2.0-dev8 — WAVESHARE 7-INCH

ONLY for ESP32-S3-Touch-LCD-7 Ver1.1, 8MB flash/8MB PSRAM.
DO NOT FLASH THIS IMAGE ON A T-QT PRO. Hardware OTA testing is pending.
Finish all SD writes and safe eject before resetting/flashing.

From project root, for the user's original dev3/app0 board:
  .venv-pio/bin/python scripts/flash-waveshare7.py --app-only /dev/ttyACM0
Close the serial console first. Enter FLASH, upload, then press RESET.
Use the UART connector for serial flashing; USB carries native HID/storage.
On Windows use flash-windows.cmd with the correct COM port and this folder's
WITS-Keyboard-Waveshare7-0.2.0-dev8.app.bin. This initial app-only update
preserves bonds on the unchanged app0 layout.

Enter HID, connect in the dev8 app, disarm, highlight the board, then Update
firmware. Select this folder's .ota.json beside its .app.bin. BLE transfers
without changing the PC's network. The display pauses during flash writes;
follow progress in the app. Keep power connected. Verified updates reboot to
PROGRAM. Check version, then enter HID again. Each unit of this model uses
the same model image. Later OTA updates must use a Waveshare manifest/image.

See RELEASE-NOTES.md and project OTA-UPDATES.md. After OTA, serial app-only
writing at 0x10000 may not update the selected slot; use OTA or factory recovery.
