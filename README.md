# WITS Deploy

A deployment toolkit from **Whitehorse IT Solutions** for entering text and
product keys, sharing installation files, and managing device firmware.

The Windows/Linux desktop app controls USB-connected ESP32 devices over paired,
encrypted Bluetooth. Each device acts as a USB keyboard; supported models also
provide MicroSD-backed USB storage.

## Features

- Control multiple devices with saved names and individual targets.
- Send text, special keys, and keyboard shortcuts with adjustable start and
  character delays.
- Physically arm devices before typing, with visible status and STOP controls.
- Share deployment files over USB mass storage on supported Waveshare boards,
  with read-only access by default and app-controlled write permission.
- Update firmware over Bluetooth or USB using one release manifest that lists
  the images for each board model.
- Install factory firmware on blank supported boards through the USB flasher.

## Hardware

| Board | Firmware target | Status |
| --- | --- | --- |
| LILYGO T-QT Pro | `tqtpro` | Supported |
| Waveshare ESP32-S3-Touch-LCD-7 Ver1.1 | `waveshare7` | Supported, including MicroSD storage |
| Waveshare ESP32-S3-Touch-LCD-1.47 | `waveshare147` | First bring-up build; hardware validation pending |

Current firmware and desktop app: **0.2.0-dev11**. Bluetooth OTA has been tested on
the T-QT Pro and 7-inch boards. The 1.47-inch port, USB update/factory installation
and interrupted-update recovery need hardware validation.

### Waveshare 1.47-inch touch board

The newest hardware target is the
[Waveshare ESP32-S3-Touch-LCD-1.47](https://docs.waveshare.com/ESP32-S3-Touch-LCD-1.47),
with a 172 × 320 capacitive touchscreen and MicroSD slot. Dev10 includes a
dedicated display/touch adapter, USB keyboard and storage, Bluetooth OTA, and
USB flashing through the same desktop app. Its first physical tests are pending;
see the [setup and test guide](docs/boards/WAVESHARE147.md). Dev11 uses a
320 × 172 landscape layout for its case, with USB-C on the right.

## Get started

Install **Python 3.11 or newer**. From the repository root, on Linux:

```bash
cd desktop
bash SETUP-LINUX.sh
bash START-LINUX.sh
```

On Windows, run `desktop/SETUP-WINDOWS.cmd`, then `desktop/START-WINDOWS.cmd`.

Put the board in HID mode and pair using the PIN on its screen. On Windows,
complete the initial pairing in Bluetooth Settings first. Connect in the app,
select the intended target, and physically arm the board when ready to type.
See the [desktop guide](desktop/README.md) for pairing and controls.

For a Linux app-menu shortcut, run `bash desktop/INSTALL-LAUNCHER-LINUX.sh` from
the repository root. Sign-in launch is optional via `--autostart`.
Windows/Linux standalone build scripts and a GitHub Actions workflow are
prepared, including all three models' firmware. The Linux native package has
passed local startup checks; Windows builds remain pending. See
[shortcuts and native packaging](docs/DESKTOP-PACKAGING.md).

## Firmware updates

- **OTA Update…** uses the connected board's model to select the correct image.
  It requires an authenticated, disarmed board running OTA-capable firmware
  (dev8 or newer).
- **USB Flash/Update…** supports working-board updates that preserve pairings,
  plus factory installation on blank boards. Choose the physical board model
  and serial port, then enter FLASH/bootloader mode. Factory installation clears
  existing board settings.

Use the common release JSON and keep its image folders alongside it. Safely
eject writable storage before updating. The 7-inch board's **UART** connector is
for USB flashing; its **USB** connector carries keyboard and storage traffic.
The 1.47-inch board uses its single USB-C connector for both roles.

[Update and recovery guide](docs/OTA-UPDATES.md) · [Release files](releases/README.md)

## Development and documentation

- [Build, test, and package releases](docs/DEVELOPMENT.md)
- [Waveshare 7-inch setup](docs/boards/WAVESHARE7.md)
- [Waveshare 1.47-inch first flash](docs/boards/WAVESHARE147.md)
- [Storage design and hardware roadmap](docs/STORAGE-PLAN.md)
- [Web controller deployment](deploy/README.md)
- [Historical handoffs](docs/handoffs/README.md)

Git tracks source, documentation, release manifests, and checksums. Generated
binaries, ZIPs, environments, and runtime logs are excluded. A source clone
needs firmware built locally or supplied as a release bundle before flashing.
