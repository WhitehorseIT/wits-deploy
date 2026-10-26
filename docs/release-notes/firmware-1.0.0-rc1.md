**Release candidate for firmware 1.0.** Testing is under way; if it finds nothing, the same code ships as 1.0.0.

## What's new
- The firmware now has its own version and release stream. It no longer changes when only the desktop app does, and it is released only when the firmware itself changes.
- The code is the same as 0.2.0-dev18 through dev22 (HID mode by default, programming mode on request, read/write storage without an eject, faster USB reads, T-QT Pro PROGRAM hold progress bar). Only the version string changed.
- Compatibility rules for the 1.x series are written down in `docs/COMPATIBILITY.md`.

## Updating
- Desktop app 0.2.0-dev23 or newer: **OTA Update… > Download latest firmware** (signed and verified), one board at a time.
- Older apps: download the firmware ZIP below, extract it, and choose its `WITS-Deploy-Release-1.0.0-rc1.ota.json` in **OTA Update…** or **USB Flash/Update…**.

## Files
- `WITS-Deploy-Firmware-1.0.0-rc1.zip` (with a `.sha256` file): firmware for the T-QT Pro, Waveshare 7-inch and Waveshare 1.47-inch.
- `release-manifest.json` and `release-manifest.json.sig`: the signed manifest the app checks.

## Being tested before 1.0
Interrupted Bluetooth updates and repeated slot alternation on all three models, blank-board factory installs, USB storage on the Waveshare 7-inch, reset and power-cycle behavior, and a long soak test.
