# Firmware updates

Use the app's **OTA Update…** (Bluetooth) and **USB Flash/Update…** (USB) buttons. Both read a release
manifest that lists the image for each board model. The firmware comes from the copy bundled with
the app, a release folder you choose, or a signed download (see below).

## One manifest, three board models

Extract the entire firmware ZIP, preserving folders, then select its
`WITS-Deploy-Release-<version>.ota.json`.
It describes app and factory images for `tqtpro`, `waveshare7` and
`waveshare147`. Each model uses a different binary; all units of the same
model share one binary. The Bluetooth updater reads authenticated board info
and selects only its matching image. Unknown or missing models stop before
upload. Local filenames, sizes and SHA-256 hashes are checked. Old single-board
schema 1 manifests still work; common catalogs use schema 2.

Board model codes are Waveshare7 = 1, T-QT Pro = 2 and Waveshare147 = 3. The release builder
generates the common catalog when all three images exist. `scripts/make-ota-catalog.py RELEASE_DIRECTORY`
can also generate a catalog for available models, including older releases.
Existing published catalogs and archives are immutable.

## First installation and USB recovery

USB Flash/Update is available without a Bluetooth selection, including blank
boards. Select the physical model, serial port and common release JSON.
Blank boards cannot identify themselves as a WITS model. The flasher requires
an ESP32-S3 and the selected flash capacity: T-QT Pro 4MB, Waveshare7 8MB,
Waveshare147 16MB. Capacity checking cannot distinguish unrelated boards with
the same chip/memory, so select the exact physical model.

Close serial monitors and enter FLASH/ROM bootloader mode. The **7-inch**
board uses its UART connector; keyboard/storage use its separate USB connector.
The **1.47-inch** board and T-QT Pro use their native USB connector. For a blank
1.47-inch board, hold BOOT, press/release RESET and release BOOT if needed.

Choose **Install blank board / factory recovery** for a first install or a
different partition layout. It writes the complete image at zero, including
bootloader, partition table and initial app selection. Existing settings and
bonds in that image range are cleared. The board-specific first-flash command
and test sequence are in [Waveshare147 setup](boards/WAVESHARE147.md).

Choose **Update working board** to preserve pairings on an existing WITS
layout. The flasher verifies the partition table against the release and reads
both OTA select entries. It validates their CRC/state, writes and explicitly
verifies the inactive app slot, then writes/verifies only the other OTA metadata
sector. The previous selected app and NVS bonds remain intact. Unconfirmed
boots or corrupt/unknown metadata refuse this path: boot normally first, or use
explicit factory recovery as appropriate. Keep power connected and press RESET
after verified success. From 0.2.0-dev17 the board then starts in HID mode with the new
version (older firmware starts in PROGRAM; enter HID from there).

Do not manually assume app0 at `0x10000` is the selected slot after OTA.
The older app-only bootstrap scripts are for known app0 layouts. Use the app's
slot-aware USB updater for later updates. Generic boards need their own target.

## Bluetooth OTA

OTA requires one initial USB installation of OTA-capable firmware (0.2.0-dev8 or newer). It uses the
paired, MITM-authenticated, encrypted BLE connection. The PC keeps its normal network connection; no
Wi-Fi hotspot is involved. The browser controller has no OTA UI.

1. Finish writes and safely eject writable storage on its target PC. Update **one board at a
   time**: Bluetooth shares airtime between connections, and an update measured 0.4 KB/s with three
   boards connected against about 12 KB/s with one. The app offers to disconnect the other boards
   first, and switches Auto-connect off on every board during the update, restoring it when the
   updater closes.
2. The board starts in HID mode (older firmware: enter HID first). Connect in the desktop
   app and leave the board DISARMED.
3. Highlight exactly one board and choose OTA Update. Click **Download latest firmware** (signed and
   verified), use the bundled firmware, or select a common JSON, then start the update. Factory images
   cannot be sent over Bluetooth.
4. Keep power connected. The app shows acknowledged progress, KiB/s and ETA,
   followed by verification. The 7-inch RGB display pauses during flash writes;
   the SPI displays retain the update message.
5. After verified success, the board reboots into HID mode (firmware older than
   0.2.0-dev17 reboots into PROGRAM; enter HID there). Check its version and reconnect.

Linux may cache the old GATT layout when moving from pre-OTA firmware. If OTA
services are missing despite a correct version, hold PAIR to display a PIN and
use the app's Re-pair action. It replaces only that computer's bond for the
chosen board and refreshes discovery. Re-pair is not required for every update.
Windows initial PIN pairing still uses Windows Bluetooth Settings.

The app refreshes the negotiated packet size and logs progress/write size.
Linux queries MTU using BlueZ's public AcquireWrite interface, closes its file
descriptor and confirms the write lock is released before normal Bleak writes.
With a single board connected, updates run at about 12 KiB/s. Measure the live rate if it looks slow:
the usual cause is several boards connected at once.

## Transfer and recovery behavior

- The board rejects updates while armed, typing or holding writable storage
  ownership. BEGIN includes a firmware-enforced board code.
- Writes go to the inactive app slot. Four packets per acknowledgment window
  fit the bounded queue; progress reflects accepted flash writes.
- Size, SHA-256 and ESP image checks must pass before boot selection changes.
  The board checks integrity only; publisher authenticity comes from the app, which verifies a signed
  manifest before it uses a downloaded image (files you pick yourself are trusted software). The
  entire image is not cached in RAM.
- Cancel, disconnect, sequence errors or 15 seconds without activity abort an
  uncommitted upload. After display/flash preparation, failure reboots to
  PROGRAM with the retained boot selection. There is no transfer resume.
- A lost final acknowledgment can happen after commit. Check the board's
  version before assuming failure. Avoid interrupting final verification.
- Storage is taken offline before flash writes. A previous writable export
  requires host safe eject. Dev13 retains the existing R/W grant through BLE
  disconnect/reconnect and app closure rather than abruptly revoking writes. A completed block write does not flush the host filesystem.
- SDK rollback is enabled. New firmware is confirmed after essential board IO,
  expected PSRAM and native USB startup, before display/BLE initialization.
  This does not prove later application behavior. Retain USB recovery access.

## Validation status

All three firmware targets compile and the desktop tests cover model selection, image and path
corruption, board codes, packet sizing, upload cancellation and errors, USB capacity and layout
checks, inactive-slot writes, and verification before boot selection. C++ compile-time checks cover
touch handling, storage policy, chunking and SCSI flush behavior. These simulate hardware.

On hardware (Linux host): Bluetooth updates, including signed downloads, work on all three boards, and
one interrupted update left the Waveshare 1.47 booting its previous firmware. Interrupted-transfer
recovery across repeated slot alternation, USB updates on Windows and Windows Bluetooth updates still
need physical validation. See each model guide for its bring-up sequence.

## Firmware version colors and the update check

The board list's **Firmware** column is highlighted against the newest known release: green is
current, yellow means an update is available, red means a critical update. At startup the app asks
GitHub for the published releases (anonymous requests; nothing about your boards is sent) and compares
each board against the newest firmware release (tags `fw-v<version>`) and the firmware bundled with the
app; app releases (tags `v<version>`) only drive **Update app…**; offline, only the bundled version is
used. To turn the check off, set the environment variable `WITS_DEPLOY_NO_UPDATE_CHECK=1`.

Red comes only from a release's **signed manifest** (`critical_below`), never from release notes.
When a release's signature verifies, **OTA Update…** also offers **Download latest firmware**: the
app downloads the firmware bundle, checks it against the signed size and SHA-256, and only then
offers it for upload. See [release signing](RELEASE-SIGNING.md).
