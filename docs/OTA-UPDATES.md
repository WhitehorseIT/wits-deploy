# Firmware updates over Bluetooth

First BLE OTA implementation: **firmware/controller 0.2.0-dev8**, for both
T-QT Pro and Waveshare ESP32-S3-Touch-LCD-7 Ver1.1. Updates use the selected
board's existing authenticated, encrypted BLE connection. The computer keeps
its Wi-Fi/Ethernet connection and internet access. No hotspot is needed.
The earlier dev4-dev7 hotspot experiments were not distributed and are superseded.

Current firmware is **dev9** (pairing countdown redraw fix), used with the
**dev9 controller**. The user completed verified dev8 OTA uploads on
both models after re-pairing: Waveshare 978,416 bytes / 80.83 seconds and T-QT Pro
889,888 bytes / 73.27 seconds. Interrupted-transfer recovery still needs a
physical test; successful full uploads alone do not prove that behavior.

When upgrading from pre-OTA firmware, Linux may retain its old GATT service
list even while reading dev8 from the board. The user resolved missing OTA/info
characteristics with the app's Re-pair action: hold PAIR until the PIN appears,
highlight that board, then Re-pair. This replaces only that computer's bond for
that board and refreshes discovery. Re-pair is not a prerequisite for every
OTA: dev9 keeps dev8's GATT layout, so the current bond should work unchanged.

## Unified release manifest and USB flasher (app dev9)

Choose `releases/firmware/0.2.0-dev9/WITS-Keyboard-Release-0.2.0-dev9.ota.json` for either
connected board. Schema 2 maps model IDs to app filename/size/SHA-256 plus an
optional factory descriptor. The app reads authenticated board info and selects
only its matching app image; unknown/missing models stop before upload. Image
paths stay inside the extracted release folder. Schema 1 manifests still work.
The builder creates the common JSON after both model builds are available;
`scripts/make-ota-catalog.py RELEASE_DIRECTORY` also creates/verifies it.

`Flash over USB` is available without a BLE connection, including blank boards.
Choose the physical model and serial port; blank boards cannot report a WITS
identity. The same release JSON provides the images. Safely eject writable
storage, cancel active OTA, close serial consoles and enter FLASH first. Use
Waveshare UART. The flasher requires an ESP32-S3 and the selected model's
expected flash capacity (4MB T-QT Pro / 8MB Waveshare7).

Working-board update checks the partition table against the release, reads
both OTA select entries, validates their CRC/state and writes the inactive slot.
After explicit esptool verification, it writes and verifies only the other
metadata sector with the next sequence/NEW state. It preserves the selected
old slot and NVS bonds, even after previous OTA selected app1. An unconfirmed
boot or corrupt/unknown selection refuses this path and requests a normal boot
or explicit factory recovery. Factory install writes the complete image at
0x0, including bootloader and partition table, clearing existing bonds/settings.
Press RESET when verification finishes. Generic boards need their own target.

The app shows speed/ETA and logs write size and progress every five seconds.
It no longer freezes an initial 12-byte data payload for an entire upload.
Linux queries the live MTU through public BlueZ AcquireWrite, immediately
releases its FD/lock, then continues through Bleak. This is a hardware-test
candidate, not a proven fix for all radio/link scheduling slowdowns. The dev9
full-size Waveshare slowdown remains unexplained. Tests use simulated devices;
real USB factory/update and updated BLE speed/recovery tests remain pending.

## Bootstrap once over USB

Existing firmware cannot receive Bluetooth updates until it has the OTA GATT
characteristics. Install dev9 once using USB. Finish any storage writes and
safe eject first; close the UART console before flashing. Enter FLASH from
PROGRAM. These app-only commands preserve bonds on the existing app0 layout
(user's dev3 Waveshare and the tester's 0.1.1 T-QT Pro):

Waveshare, from this project root:

```bash
.venv-pio/bin/python scripts/flash-waveshare7.py --app-only /dev/ttyACM0
```

T-QT Pro (adjust serial port as needed):

```bash
$HOME/.platformio/packages/tool-esptool/esptool --chip esp32s3 --port /dev/ttyACM0 --baud 460800 write-flash 0x10000 releases/firmware/0.2.0-dev9/tqtpro/WITS-Keyboard-0.2.0-dev9.app.bin
```

On Windows use this release's flash-windows.cmd with the correct COM port
and the matching model's .app.bin. Press RESET after upload; verify dev9 on
PROGRAM. Hold HID for two seconds, then connect using the updated app. If the
OS cached the old service list, disconnect/reconnect first; an OS re-pair may
be needed if it still cannot discover the new OTA characteristics.

## Later updates from the app

1. Finish writes and safely eject writable SD storage on its deployment PC.
2. Enter HID, connect the board in the desktop app and leave it DISARMED.
3. Highlight exactly one board and click Update firmware.
4. Choose the matching `.ota.json` beside its `.app.bin`, then Upload and restart.
   Select the T-QT Pro or Waveshare image as appropriate; one binary serves
   all units of the same model. A factory image cannot be uploaded through OTA.
5. Keep power connected. Progress reflects acknowledged flash writes, followed
   by device size/SHA-256/ESP image verification. The Waveshare display pauses
   during flash writes; the T-QT Pro retains its Bluetooth update message.
6. After verification, the board restarts in PROGRAM. Check the displayed
   version and enter HID again. No computer network change is necessary.

Use the dev9 manifest/image for the next upload to fix countdown flicker.
A repeat update can exercise the alternate OTA slot. Test cancellation and interrupted transfer as well. Do not
interrupt after the app says it is verifying. With Waveshare UART already
open, look for `[WITS OTA] boot confirmation: ESP_OK` after the OTA reboot.
Opening UART later may pulse reset, so keep the console open across a test.

## Transfer and recovery behavior

- Only the paired, MITM-authenticated BLE connection may access the three OTA
  characteristics. The board rejects updates while armed/typing. The app
  checks model identity; BEGIN also contains a firmware-enforced model code.
- Writes target the inactive OTA slot. Four packets per acknowledgment window
  fit the bounded device queue. The app uses the negotiated write size (up to
  504 image bytes per packet); progress acknowledges actual Update.write calls.
- SHA-256, length and ESP image validation must pass before changing boot
  selection. This checks integrity, not publisher signatures. Treat firmware
  files as trusted software. The hosted browser console has no OTA interface.
- Cancel, disconnect, sequence errors or 15 seconds without transfer activity
  abort an uncommitted upload. Once flash preparation has paused the display,
  failure reboots into PROGRAM using the retained boot selection. There is no
  resume support; reconnect and start again. A lost final acknowledgment can
  occur after commit: check the board's version rather than assuming failure.
- Waveshare takes media offline before flash writes. A previous writable
  export still requires host eject even if the BLE write grant was revoked.
  SD writes/unmount jobs must finish before resetting or serial flashing too.
- The SDK enables rollback. A new image is confirmed after essential board IO,
  expected PSRAM and native USB startup, before RGB starts. Failed essential
  checks request rollback. This does not test later display/BLE/application
  behavior; retain USB recovery access while testing development releases.
- After OTA selects app1, serial app-only flashing at 0x10000 still writes
  app0 and does not change the selected slot. Use OTA for subsequent updates;
  serial recovery must account for the selected slot or use a matching factory
  image (which clears bonds). The bootstrap commands above target app0 only.
- Build manifests with `scripts/build-release.sh VERSION [tqtpro|waveshare7]`.
  Keep each manifest and image together. Never use the other board's image.

## Validation status

Both firmware targets build. Automated tests cover image corruption and path/
factory rejection, negotiated packet size and payload integrity, board codes,
legacy firmware rejection, cancellation/disconnect, device errors and verified
completion, plus Qt progress wiring. Compile-time C++ assertions cover storage
policy, chunk boundaries and SCSI flush behavior. Full dev8 BLE uploads were verified on both physical models (times above).
Repeated slot alternation, interrupted-upload recovery, post-update HID and
the dev9 display changes still require physical checks. Existing 0.1.1 keyboard functions remain compatible
with this app, but require the USB bootstrap before OTA becomes available.
