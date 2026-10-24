WAVESHARE ESP32-S3-TOUCH-LCD-7 VER1.1 FIRMWARE 0.2.0-dev9

Use the existing dev8 desktop app. Safely eject writable SD storage, connect
and disarm this Waveshare, highlight its row and choose Update firmware.
Select WITS-Keyboard-Waveshare7-0.2.0-dev9.ota.json beside its .app.bin.
Keep power connected; RGB pauses during upload. The board restarts in PROGRAM;
verify dev9, hold HID, reconnect and test the pairing countdown.

This image is NOT for T-QT Pro. GATT layout is unchanged from dev8, so another
Re-pair should not be required. See RELEASE-NOTES.md for checks and limitations.
Use OTA after the initial bootstrap; app-only serial writes at 0x10000 may
update the inactive app0 slot after a previous OTA selected app1.
