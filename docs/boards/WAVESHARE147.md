# Waveshare ESP32-S3-Touch-LCD-1.47

Firmware target `waveshare147` (Bluetooth update code 3). It has been tested for pairing, typing,
USB storage, Bluetooth and USB updates on a Linux host. Interrupted-update recovery and Windows
testing are still open; see the [status](../../README.md#status-and-limitations).

## Hardware

For the **ESP32-S3-Touch-LCD-1.47**: JD9853 172 × 320 LCD, AXS5106L touch, 16 MB flash, 8 MB octal
PSRAM, MicroSD slot and one native USB-C connector. Use this board's own image. The non-touch S3 LCD
board and the C6 board have different hardware.

| Function | GPIO |
| --- | --- |
| LCD DC / CS / SCK / MOSI | 45 / 21 / 38 / 39 |
| LCD reset / backlight | 40 / 46 |
| Touch SDA / SCL / reset / interrupt | 42 / 41 / 47 / 48 |
| SD CS / MOSI / SCK / MISO | 14 / 15 / 16 / 17 |
| BOOT button | 0 |
| Native USB D− / D+ | 19 / 20 |

The LCD uses SPI3 and the SD card uses SPI2, so they do not share a controller. The SD pins are not
the chip's direct SPI2 pins, so the signals go through the GPIO matrix, which limits reliable clock
speeds. The LCD's RAM column offset is 34. The layout is 320 × 172 landscape (rotation 1) with USB-C on
the right. Touch uses I²C address 0x63; raw portrait coordinates map to landscape as `x = rawY,
y = rawX`. Status and PIN occupy the left panel; PAIR/STOP, ARM/DISARM/CLEAR and PROG occupy the right.

Pin assignments come from the [manufacturer schematic](https://files.waveshare.com/wiki/ESP32-S3-Touch-LCD-1.47/ESP32-S3-Touch-LCD-1.47-Schematic.pdf).
LCD reset is **GPIO40**, distinct from the touch reset on GPIO47. JD9853 register settings and AXS5106L
report decoding follow the [vendor-linked Arduino example mirror](https://github.com/VolosR/Wave147moreExamples/tree/5c05f2eb5429b49f6829f37b67db9dd0e69b88ef/TurboBlink).
See also the [manufacturer board guide](https://docs.waveshare.com/ESP32-S3-Touch-LCD-1.47) and
[resources](https://docs.waveshare.com/ESP32-S3-Touch-LCD-1.47/Resources-And-Documents).

## First flash

Use the board's **single USB-C connector**. If needed, hold BOOT, press and release RESET, then
release BOOT to enter the ROM loader. Close serial monitors.

**With the app (recommended):** open **USB Flash/Update…**, choose **Waveshare 1.47-inch touch**, the
board's serial port and a release JSON (the bundled one is preselected), and select **Install blank
board / factory recovery**. This clears existing board settings.

**With the helper script,** from the repository root on Linux, with the release extracted under
`releases/firmware/<version>/` (download the firmware ZIP from the GitHub release):

```bash
.venv-pio/bin/python scripts/flash-waveshare147.py /dev/ttyACM0 --version <version>
```

Replace the port if necessary. The helper verifies file hashes, requires an ESP32-S3 with exactly 16 MB
flash, installs the complete factory image at zero and verifies the written contents.

Press RESET after success. The board starts in HID mode and shows the new version number. For the first
test, begin without a MicroSD card.

## Controls

In HID mode the screen has PAIR, STOP, ARM/DISARM, CLEAR and PROG controls. PAIR and PROG need a
two-second hold; CLEAR needs five seconds and shows a confirmation without opening pairing. Hold bars
show progress. ARM/DISARM is a tap after an authenticated connection; STOP acts on touch-down. Sliding
off a control cancels it, and multiple contacts, invalid coordinates or a missing touch report cancel
the gesture instead of arming on release. The PIN and pairing countdown use separate lines.

Hold **PROG** for two seconds to enter programming mode. In programming mode, hold **HID** for two
seconds to return, or **FLASH** for the ROM loader. The bootloader message stays on the screen until a
reset.

The BOOT button is a fallback: hold two seconds and release to enter HID from programming mode or open
pairing from HID. Pressing it in HID stops typing at once. Release it before the mode switch so GPIO0
is not held low at reset.

A first check: the display, four touch corners, hold bars and cancel behavior. Then pairing, PIN
visibility, Ping, Identify, physical ARM, sample text, STOP and PROG.

## Storage

Add an expendable card once keyboard operation works, reset, and enter HID. Storage starts read-only;
the app grants read/write. See [USB storage](../STORAGE.md) for the behavior and limits. Reads are
about 0.9 MB/s and writes about 0.4 MB/s. The firmware does not format or repair cards.

## Updates and partitions

Update over Bluetooth with **OTA Update…**, or over USB with **USB Flash/Update… > Update working
board**, which keeps the existing partition layout and pairings. Both use the inactive app slot and
validate size and SHA-256 before selecting it. See [firmware updates](../OTA-UPDATES.md).

The 16 MB layout has app slots at `0x10000` and `0x650000`, each `0x640000` bytes, with boot selection
metadata at `0xe000`. USB updates verify the existing partition table before writing the inactive slot;
factory installation is the recovery path for a different layout. Do not overwrite app0 manually after an
OTA without checking which slot is selected.

## Build

```bash
.venv-pio/bin/pio run -e waveshare147
bash scripts/build-release.sh <version> waveshare147
```

Generated files go to `releases/firmware/<version>/waveshare147/`. The common JSON chooses the binary by
model, not by a device's friendly name; every unit of this model uses the same binary.
