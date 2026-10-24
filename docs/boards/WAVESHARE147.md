# Waveshare ESP32-S3-Touch-LCD-1.47

The `waveshare147` target uses firmware **0.2.0-dev12**. The user confirmed
pairing and operation on the landscape dev11 build. Dev12 enlarges the version
label, two-line guidance beneath the ID, pairing instructions, Identify aliases
and storage status. The PIN/countdown retain separate lines. This font update
still needs physical inspection; storage and interrupted-update tests remain
pending. Existing desktop app dev11 can load the dev12 JSON without rebuilding.

## Hardware

This port is for the **ESP32-S3-Touch-LCD-1.47** with JD9853 172 × 320 LCD,
AXS5106L touch, 16 MB flash and 8 MB octal PSRAM. Use this board's own image.
The non-touch S3 LCD board and the C6 board have different hardware.

| Function | GPIO |
| --- | --- |
| LCD DC / CS / SCK / MOSI | 45 / 21 / 38 / 39 |
| LCD reset / backlight | 40 / 46 |
| Touch SDA / SCL / reset / interrupt | 42 / 41 / 47 / 48 |
| SD CS / MOSI / SCK / MISO | 14 / 15 / 16 / 17 |
| BOOT button | 0 |
| Native USB D− / D+ | 19 / 20 |

The LCD uses HSPI/SPI3 and SD uses SPI2, so the two drivers do not compete
for the same SPI controller. The LCD's RAM column offset is 34. Dev11 uses rotation 1 with a 320 × 172
landscape layout, configured for USB-C on the right as requested for the case.
Touch uses I²C address 0x63; raw portrait coordinates map to landscape as
`x = rawY, y = rawX`, matching that LCD rotation. Status and PIN occupy the
left panel; PAIR/STOP, ARM/DISARM/CLEAR and PROG occupy the right panel.
Both physical orientation and touch alignment need checking on the first unit.
The user's saved MakerWorld page and `ESP32_S3_147_Complete_Plate_X1C_PLA.3mf`
were inspected for the landscape case/stand arrangement. Case assembly and
clearance have not been physically verified.

Pin assignments come from the [manufacturer schematic](https://files.waveshare.com/wiki/ESP32-S3-Touch-LCD-1.47/ESP32-S3-Touch-LCD-1.47-Schematic.pdf).
LCD reset is **GPIO40**, distinct from the touch reset on GPIO47; one example
uses a misleading LCD reset argument. JD9853 register settings and AXS5106L
report decoding follow the [vendor-linked Arduino example mirror](https://github.com/VolosR/Wave147moreExamples/tree/5c05f2eb5429b49f6829f37b67db9dd0e69b88ef/TurboBlink).
See also the [manufacturer board guide](https://docs.waveshare.com/ESP32-S3-Touch-LCD-1.47)
and [resources](https://docs.waveshare.com/ESP32-S3-Touch-LCD-1.47/Resources-And-Documents).

## First flash

Use the board's **single USB-C connector**. If needed, hold BOOT, press and
release RESET, then release BOOT to enter the ROM loader. Close serial monitors.
From the repository root on Linux, with the complete dev12 release available:

```bash
.venv-pio/bin/python scripts/flash-waveshare147.py /dev/ttyACM0
```

Replace the port if necessary. The helper verifies file hashes, requires an
ESP32-S3 and exactly 16 MB flash, installs the complete factory image at zero,
and verifies the written contents. This clears existing board settings.
Press RESET after success. Expect a blue **PROGRAM** screen and version
**0.2.0-dev12**. This is the first physical test, so begin without a MicroSD card.

Alternatively, use desktop app dev10 **USB Flash/Update…**, select
**Waveshare 1.47-inch touch**, the board's serial port and the common release
JSON. Choose **Install blank board / factory recovery** for the first flash.
Earlier apps do not know this target. On Windows, setup installs esptool;
initial Bluetooth PIN entry still uses Windows Bluetooth Settings.

## Controls and first tests

In PROGRAM, hold **HID** for two seconds to start; hold **FLASH** for the ROM
loader. The bootloader message remains on the SPI screen until reset.

In HID mode, the screen has PAIR, STOP, ARM/DISARM, CLEAR and PROG controls.
PAIR and PROG require two seconds; CLEAR requires five seconds and shows a
confirmation without opening pairing. Hold bars show progress. ARM/DISARM is
a tap after an authenticated connection; STOP takes effect on touch-down.
Sliding off a control cancels it. Multiple contacts or invalid coordinates
cancel the gesture rather than arming on release. Missing touch reports time
out and cancel the gesture. The PIN and pairing countdown occupy separate lines.

The BOOT button is a fallback: hold two seconds and release to enter HID from
PROGRAM or open pairing from HID. Pressing it in HID immediately stops typing.
Release is required before the mode switch so GPIO0 is not held low at reset. Dev11 places FLASH above HID in the right
panel in PROGRAM; in HID the full-width PROG button is below the other controls.

Check the display, four touch corners, hold bars and cancel behavior first.
Then test pairing, PIN visibility, Ping, Identify, physical ARM, sample text,
STOP and PROG. Reset should always return to PROGRAM. Add an expendable SD card
after keyboard operation passes, reset and enter HID again. Check read-only
mounting, host safe eject, app remount and a small read/write copy. There is no
filesystem formatting or automatic card repair in the firmware.

Storage starts read-only. Read/write permission requires authentication and
a disarmed board. Safely eject on the target PC before changing mode, rebooting
or updating. SPI SD and full-speed USB impose throughput limits; measure this
unit rather than assuming USB flash-drive speeds.

## Updates and build

For a working dev10 board, test the app update path: enter FLASH, choose
**USB Flash/Update → Update working board**, the new dev12 common JSON,
Waveshare 1.47-inch touch and its serial port. This keeps the existing WITS
partition layout and pairings. Desktop app dev10 remains compatible; no new
app package is needed for the display rotation.

The model reports `waveshare147`, with Bluetooth OTA target code 3. OTA uses the
inactive app slot and validates size/SHA-256 before selecting it. The existing
T-QT Pro and Waveshare7 target codes remain unchanged. A successful update
returns to PROGRAM; physical tests of interrupted updates remain outstanding.

The 16 MB partition layout has app slots at `0x10000` and `0x650000`, each
`0x640000` bytes, with OTA selection metadata at `0xe000`. Desktop USB updates
verify the existing partition table before writing the inactive slot; factory
installation is the recovery path for a different layout. Do not manually
overwrite app0 after OTA without checking which slot is selected.

```bash
.venv-pio/bin/pio run -e waveshare147
bash scripts/build-release.sh 0.2.0-dev12 waveshare147
```

Generated files live under `releases/firmware/0.2.0-dev12/waveshare147/`.
The app's common JSON chooses the binary by model, not by a device's friendly
name. Every unit of this exact model uses the same binary.
