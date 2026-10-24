# Firmware 0.1.1 — startup version label

The blue PROGRAM startup screen now shows FIRMWARE and a readable 0.1.1
above the hold-progress tracks. The programming CDC boot log also prints
the firmware version. No splash delay is added. The desktop app remains
0.1.0 and the BLE protocol is unchanged.

`src/firmware_version.h` supplies the version. The release builder checks
that a named release matches it and refuses to overwrite existing images.

This release is for the LILYGO T-QT Pro only. Waveshare touchscreen and
MicroSD/USB mass-storage support are not included.

Build passed; merged factory bootloader retains DIO. Physical display
verification remains pending. Update a working board with the app-only
image at 0x10000 to preserve Bluetooth bonds. Enter FLASH mode from the
blue screen, upload, then press RESET. The factory image is for a fresh
board and may clear bonds.
