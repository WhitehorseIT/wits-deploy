WITS KEYBOARD 0.2.0-dev8 — T-QT PRO

This folder's WITS-Keyboard-0.2.0-dev8 images are ONLY for the T-QT Pro.
The waveshare7 subfolder contains DIFFERENT images for the 7-inch board.
This development release adds Bluetooth OTA; hardware tests are pending.

Initial USB bootstrap from T-QT Pro 0.1.1:
Enter FLASH (hold left control for two seconds from PROGRAM), then on Windows:
  flash-windows.cmd COM5 WITS-Keyboard-0.2.0-dev8.app.bin
Adjust COM5. Use .app.bin to preserve bonds with the existing app0 layout.
Press RESET after upload. Verify dev8, enter HID, connect using the dev8 app.

Later OTA: highlight the connected, authenticated, disarmed board, click Update
firmware and choose WITS-Keyboard-0.2.0-dev8.ota.json (keep its .app.bin beside
it). This does not change Wi-Fi or internet access. One image works on all
T-QT Pro units. Keep power connected. The board restarts in PROGRAM afterward.

SHA256SUMS.txt verifies both binaries. RELEASE-NOTES.md and the project
OTA-UPDATES.md explain validation, cancellation and recovery limitations.
After OTA, app0-only serial flashing may not update the selected boot slot.
