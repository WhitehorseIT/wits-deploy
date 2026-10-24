# WITS Keyboard

Whitehorse IT Solutions' deployment keyboard: enter text, product keys and
special-key combinations on deployment machines through a USB HID device,
controlled from a paired Bluetooth desktop application.

## Current status

- Firmware and desktop development version: **0.2.0-dev9**.
- Supported boards: **LILYGO T-QT Pro** and **Waveshare ESP32-S3-Touch-LCD-7 Ver1.1**.
- Bluetooth OTA uploads have succeeded on both boards. The updated Linux
  MTU preparation restored full-size packets and improved observed throughput.
- USB update/factory installation and interrupted-transfer recovery still
  need hardware validation. The automated suite has 110 passing tests.
- ESP32-S3-Touch-LCD-1.47 support is planned; no image for it is available yet.

## Desktop controller

Python 3.11 or newer is required. On Linux:

```bash
cd desktop
bash SETUP-LINUX.sh
bash START-LINUX.sh
```

On Windows, run `desktop/SETUP-WINDOWS.cmd`, then `desktop/START-WINDOWS.cmd`.
See [desktop instructions](desktop/README.md) for pairing, targeting, send
delays and diagnostics. Boards connect disarmed; arming is a physical action.

## Firmware updates

Use **OTA Update…** for a connected, authenticated, disarmed board. Select the
common release manifest; the app reads the board model and chooses its matching
image. Bluetooth OTA requires firmware dev8 or newer, installed once over USB.

Use **USB Flash/Update…** without a Bluetooth connection. Select the physical
board model, serial port and the same release manifest, then choose:

- **Update working board:** verify the layout, write and verify the inactive
  app slot, then update the other OTA selection sector. Existing pairings remain.
- **Install blank board / factory recovery:** install the complete factory
  image, including bootloader and partition table; existing settings are cleared.

Enter FLASH/bootloader mode first for USB flashing. The Waveshare's **UART**
connector is used for programming; its **USB** connector carries HID/storage.
Safely eject writable storage and finish/cancel any OTA transfer before switching
to USB flashing. Follow the [update and recovery guide](docs/OTA-UPDATES.md).

## Project layout

```text
src/                         Shared firmware and board adapters
desktop/                     Python controller, setup scripts and tests
web/                         Browser-based keyboard controller
deploy/                      Static site and Cloudflare Tunnel deployment
scripts/                     Build, package, flash and diagnostic tools
tests/                       Firmware compile-time checks
docs/                        Current guides and hardware plans
  boards/                    Board-specific documentation
  handoffs/                  Historical development snapshots
releases/
  firmware/<version>/
    tqtpro/                  T-QT Pro binaries, manifests and flashing notes
    waveshare7/              Waveshare 7-inch binaries and related information
    WITS-Keyboard-Release-<version>.ota.json
    WITS-Keyboard-Firmware-<version>.zip
  desktop/<version>/         App ZIP, instructions and archive checksum
```

Generated binaries and ZIPs are kept locally and ignored by Git. Source,
instructions, release manifests and checksums are tracked. See the
[release layout](releases/README.md). Existing archives retain their original
contents; future packages use the organized board folders.

## Build and verify

With PlatformIO installed in `.venv-pio`, from this directory:

```bash
.venv-pio/bin/pio run -e tqtpro -e waveshare7
bash scripts/build-release.sh VERSION tqtpro
bash scripts/build-release.sh VERSION waveshare7
```

`VERSION` must match `src/firmware_version.h`. Releases are written to the
model's folder under `releases/firmware/VERSION/`. Once both builds exist, a
common release manifest is generated automatically. Existing binaries are not
overwritten. To package a release:

```bash
python3 scripts/package-ota-release.py releases/firmware/VERSION/WITS-Keyboard-Release-VERSION.ota.json
python3 scripts/package-controller.py
```

The app packager uses the version in `desktop/wits_keyboard/__init__.py` and
requires `releases/desktop/VERSION/README-FIRST.txt` beforehand.

Run desktop tests after setup:

```bash
cd desktop
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests
```

## Documentation

- [Firmware updates and recovery](docs/OTA-UPDATES.md)
- [Waveshare 7-inch setup](docs/boards/WAVESHARE7.md)
- [Storage design and planned 1.47-inch board](docs/STORAGE-PLAN.md)
- [Historical handoffs](docs/handoffs/README.md)
- [Web deployment](deploy/README.md)
