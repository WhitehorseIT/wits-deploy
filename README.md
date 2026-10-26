# WITS Deploy

A deployment toolkit from **Whitehorse IT Solutions** for entering text and product keys on
other computers, sharing installation files, and managing the device firmware that does it.

A desktop app (Linux and Windows) controls USB-connected ESP32-S3 boards over paired, encrypted
Bluetooth. Each board shows up to the target computer as a USB keyboard; boards with a MicroSD
slot also appear as a USB drive.

> **Status: test builds.** The desktop app is at `0.2.0-dev` pre-release versions and the firmware is a
> release candidate for 1.0. The Linux app and all three supported boards are tested on real hardware;
> Windows testing is in progress. See [Status and limitations](#status-and-limitations).

## Features

- Control several boards at once, with saved names, per-board targets and optional automatic
  reconnect.
- Send text, special keys and keyboard shortcuts, with adjustable start and character delays.
- Arm each board physically before it will type, with visible status and STOP controls.
- Share deployment files over USB mass storage on the Waveshare boards: read-only by default, with
  write access granted from the app. The boards use full-speed USB (about 0.9 MB/s reading and
  0.4 MB/s writing), so this suits scripts, answer files, drivers and small installers, not large
  OS images.
- Update firmware over Bluetooth or USB. Firmware can come from the app's bundled copy, a file you
  choose, or a signed download from the project's releases.
- Install factory firmware on blank boards with the USB flasher.
- Highlighted firmware versions in the board list (green current, yellow update available, red
  critical), an update check at startup, and in-app updates for the packaged Linux build.

## Hardware

| Board | Firmware target | Storage |
| --- | --- | --- |
| LILYGO T-QT Pro | `tqtpro` | No |
| Waveshare ESP32-S3-Touch-LCD-7 Ver1.1 | `waveshare7` | MicroSD |
| Waveshare ESP32-S3-Touch-LCD-1.47 | `waveshare147` | MicroSD |

Each model needs its own firmware image; all units of one model share an image. The firmware and the
app have separate versions and releases (see [compatibility](docs/COMPATIBILITY.md)). Board guides:
[Waveshare 7-inch](docs/boards/WAVESHARE7.md), [Waveshare 1.47-inch](docs/boards/WAVESHARE147.md).

### Where to buy

These links go to each manufacturer's own product page. **They are not partner,
affiliate, or referral links, and Whitehorse IT Solutions earns nothing from them.**
Variants and prices change, so confirm the details below before ordering.

| Board | Official page | Buy this variant |
| --- | --- | --- |
| LILYGO T-QT Pro | [lilygo.cc/en-us/products/t-qt-pro](https://lilygo.cc/en-us/products/t-qt-pro) | A model with the **ESP32-S3FN4R2** chip (4 MB flash, 2 MB PSRAM). Header and case options do not matter. Avoid the ESP32-S3FN8 models, which have no PSRAM. |
| Waveshare ESP32-S3-Touch-LCD-7 | [waveshare.com/esp32-s3-touch-lcd-7.htm](https://www.waveshare.com/esp32-s3-touch-lcd-7.htm) | A **touch** version. The non-touch ESP32-S3-LCD-7 will not work with the touch controls. The firmware targets this base model, not the 7B or 7C boards. |
| Waveshare ESP32-S3-Touch-LCD-1.47 | [waveshare.com/esp32-s3-touch-lcd-1.47.htm](https://www.waveshare.com/esp32-s3-touch-lcd-1.47.htm) | The standard version, or the `-M` version with pin headers. |

Manufacturer documentation:
[T-QT Pro](https://github.com/Xinyuan-LilyGO/T-QT),
[Waveshare 7-inch](https://docs.waveshare.com/ESP32-S3-Touch-LCD-7),
[Waveshare 1.47-inch](https://docs.waveshare.com/ESP32-S3-Touch-LCD-1.47).

## Install the desktop app

### Linux (packaged build)

Download `WITS-Deploy-<version>-Linux-x86_64.tar.gz` and its `.sha256` file from the newest app
release (tagged `v<version>`) on the [releases page](https://github.com/WhitehorseIT/wits-deploy/releases), then:

```bash
sha256sum -c WITS-Deploy-<version>-Linux-x86_64.tar.gz.sha256
mkdir -p ~/Apps && tar xzf WITS-Deploy-<version>-Linux-x86_64.tar.gz -C ~/Apps
cd ~/Apps/WITS-Deploy-<version>-Linux-x86_64 && bash INSTALL-LAUNCHER.sh
```

This adds **WITS Deploy** to your application menu. No Python is needed. Later versions install
from inside the app (**Update app…**); see [packaging and updates](docs/DESKTOP-PACKAGING.md).
Linux needs BlueZ (the system Bluetooth service) and, for USB flashing, permission to use serial
ports.

### Windows (run from Python)

Windows binaries are not published: they would be unsigned and trigger SmartScreen warnings.
Instead, run the app from source with Python:

1. Install 64-bit **Python 3.11 or newer** from python.org, including the *py launcher*.
2. Download the repository (`git clone https://github.com/WhitehorseIT/wits-deploy.git` or
   *Download ZIP*). For a ZIP, **extract it first** (right-click, *Extract All*); the scripts do not work
   from inside the ZIP. Then open the extracted `desktop` folder.
3. Run `SETUP-WINDOWS.cmd` once, then `START-WINDOWS.cmd` to start the app.

Hold a board's pairing button until a PIN shows on its screen, then choose **Connect** in the app and type
the PIN into its prompt. If that does not work, pair the board in Windows **Settings > Bluetooth & devices**
first and then connect in the app. Pairing from inside the app on Windows is new and still being tested;
see the [desktop guide](desktop/README.md).

### From source (any platform)

```bash
cd desktop
bash SETUP-LINUX.sh      # creates .venv and installs the dependencies
bash START-LINUX.sh
```

## Set up a board

1. **Flash it.** Use the app's **USB Flash/Update…** with *Install blank board / factory recovery*,
   choosing the exact board model. [Update and recovery guide](docs/OTA-UPDATES.md).
2. **Pair it.** A board starts in HID mode and shows a PIN when pairing. Connect from the app and
   enter the PIN, then choose the target and physically arm the board when ready to type. See the
   [desktop guide](desktop/README.md#pairing).

### Starting modes

From 0.2.0-dev17 every board starts in **HID mode** (keyboard, Bluetooth control and, on supported
boards, USB storage), disarmed. **Programming mode** (USB serial, for flashing) is entered on
request:

- **Touch boards (Waveshare 7-inch and 1.47-inch):** hold **PROG** on the HID screen for 2 seconds.
- **T-QT Pro:** hold **both buttons** for 3 seconds; a progress bar shows the hold.
- Any crash or hang also starts programming mode, so a firmware fault cannot trap the board as a
  keyboard in a boot loop. A blank or unresponsive board can always be recovered with the USB
  flasher by holding BOOT while pressing RESET.

From programming mode, choose **HID** (touch) or hold the right button (T-QT Pro) to go back.

## Firmware updates

- **OTA Update…** sends firmware over the paired Bluetooth link to one connected, disarmed board.
  It uses the board's model to pick the right image. **Download latest firmware** fetches a signed
  release; bundled and manually chosen firmware also work.
- **USB Flash/Update…** updates a working board (keeping its pairings) or installs factory
  firmware on a blank one.
- Update one board at a time: Bluetooth shares airtime between connections, and the app switches
  Auto-connect off for every board while an update runs.
- Safely eject writable USB storage on the computer before updating.

Releases are signed, and the app checks every download against the signed manifest before using it;
see [release signing](docs/RELEASE-SIGNING.md). [Update and recovery guide](docs/OTA-UPDATES.md) ·
[Release files](releases/README.md)

## Status and limitations

- **Tested on hardware (Linux host):** pairing, typing, auto-reconnect, Bluetooth and signed-download
  updates on all three boards, USB storage on the Waveshare 1.47-inch, and in-app updates of the
  Linux build.
- **Firmware 1.0:** `1.0.0-rc1` is the release candidate; the remaining checks before 1.0 are interrupted
  updates on every model, factory installs, Waveshare 7-inch USB storage, reset behavior and a soak test.
- **Still to test:** the Windows app (pairing, auto-reconnect, updates, USB flashing), interrupted
  Bluetooth updates, and USB storage on the Waveshare 7-inch.
- USB storage is limited by full-speed USB; see the [storage notes](docs/STORAGE.md).
- Plans are in the [roadmap](docs/ROADMAP.md): web interface, mobile apps, Windows installer.

## Development and documentation

- [Desktop app guide](desktop/README.md)
- [Build, test, and release](docs/DEVELOPMENT.md)
- [Packaging and app updates](docs/DESKTOP-PACKAGING.md)
- [Firmware updates and recovery](docs/OTA-UPDATES.md)
- [Compatibility promises](docs/COMPATIBILITY.md)
- [Release signing](docs/RELEASE-SIGNING.md)
- [USB storage design](docs/STORAGE.md) and [benchmark](docs/STORAGE-BENCHMARK.md)
- [Roadmap](docs/ROADMAP.md)

Git tracks source, documentation, release manifests, and checksums. Generated binaries, ZIPs,
environments, and runtime logs are excluded; releases carry the binaries.

## License and security

WITS Deploy is released under the [MIT License](LICENSE). Third-party components keep their own
licenses. To report a vulnerability, see the [security policy](SECURITY.md).
