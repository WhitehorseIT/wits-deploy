T-QT PRO FIRMWARE 0.2.0-dev9

Use the existing dev8 desktop app. Connect and disarm this T-QT Pro, highlight
its row and choose Update firmware. Select WITS-Keyboard-0.2.0-dev9.ota.json
beside WITS-Keyboard-0.2.0-dev9.app.bin. Keep power connected. The board restarts
in PROGRAM; verify dev9, hold HID, reconnect and test the pairing countdown.

This folder's images are for T-QT Pro ONLY. Waveshare images are in waveshare7/.
No service-layout change from dev8: another Re-pair should not be required.
See RELEASE-NOTES.md for validation and recovery limitations. After any OTA,
app-only serial writing at 0x10000 may target the inactive app0 slot; use OTA.
