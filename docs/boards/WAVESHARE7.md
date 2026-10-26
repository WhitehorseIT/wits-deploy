# Waveshare ESP32-S3-Touch-LCD-7 (Ver1.1)

Firmware target `waveshare7` (Bluetooth update code 1). Pairing, typing, touch controls and Bluetooth
and USB updates work. **USB mass storage on this board has not been tested on recent firmware**; the
storage design is shared with the 1.47-inch board, which has been tested. See the
[status](../../README.md#status-and-limitations).

## Hardware

An ESP32-S3 with 8 MB quad flash and 8 MB PSRAM, an 800 × 480 RGB touchscreen and a MicroSD slot. Use
the **touch** model; this is the base ESP32-S3-Touch-LCD-7, not the 7B or 7C. The board has two USB
connectors:

- **UART** (USB-to-serial): for USB flashing and boot/panic output.
- **USB** (native): carries the keyboard and mass storage to the target computer.

Manufacturer base-model pins used by the firmware:

- RGB LCD on GPIO 0/1/2/3/5/7/10/14/17/18/21/38/39/40/41/42/45/46/47/48; GT911 touch over I²C
  (SDA 8, SCL 9, IRQ 4).
- A CH422G expander controls TP_RST (1), backlight (2), LCD_RST (3), SD_CS (4) and USB_SEL (5).
- SD over SPI on MOSI 11, SCK 12, MISO 13, on a dedicated bus with the expander's chip select held low,
  matching the vendor example. Raw ESP-IDF sector I/O avoids mounting the filesystem locally.
- 8 MB partition layout, octal 8 MB PSRAM, RGB clock 16 MHz with a bounce buffer.

References: [manufacturer documentation](https://docs.waveshare.com/ESP32-S3-Touch-LCD-7),
[SD example](https://github.com/waveshareteam/ESP32-S3-Touch-LCD-7/tree/bc51a84b30c0cea018fee6e0d7427ec10102060e/examples/Arduino/examples/03_SD_Test) and
[board definition](https://github.com/waveshareteam/ESP32-S3-Touch-LCD-7/blob/bc51a84b30c0cea018fee6e0d7427ec10102060e/examples/Arduino/libraries/ESP32_Display_Panel/src/board/supported/waveshare/BOARD_WAVESHARE_ESP32_S3_TOUCH_LCD_7.h).
The published schematic is marked V1.2; this port uses the shared base-model example wiring and is
tested on a Ver1.1 board.

## Flash and start

**With the app (recommended):** put the board in ROM bootloader mode, open **USB Flash/Update…**, choose
the Waveshare 7-inch model and the **UART** port, and select *Install blank board / factory recovery*
(this clears settings) or *Update working board* (keeps pairings).

**With the helper script,** from the repository root, with the release extracted under
`releases/firmware/<version>/`:

```bash
.venv-pio/bin/python scripts/flash-waveshare7.py [/dev/ttyACM0] --version <version>
```

It verifies the image SHA-256, checks for an ESP32-S3 with at least 8 MB flash, and writes the factory
image at 0x0 (use `--app-only` to write only the app at 0x10000 and preserve bonds on a layout that is
still on app0; after any OTA use the app's slot-aware update instead).

Press RESET after flashing. The board starts in HID mode with the version on screen. Insert a preloaded
MicroSD card before entering HID if you want storage. Use the **native USB** port for the keyboard and
drive, not the UART connector.

Touch controls in HID mode: hold PAIR for 2 seconds, tap ARM/DISARM after authentication, STOP acts
immediately, hold CLEAR for 5 seconds to clear bonds, hold **PROG** for 2 seconds to enter programming
mode (safely eject writable storage first). In programming mode, hold HID for 2 seconds to return, or
FLASH for the ROM download mode. Hold bars show progress and the pairing PIN stays readable on screen.

## Storage from the desktop app

Highlight one connected board; the storage controls act on it independently of the Target boxes. The
status line shows the firmware version, card capacity and access mode. To enable writes, disarm the
board and click **Mount read/write**; the drive briefly disappears and returns writable, with no eject
needed. To go back to read-only, safely eject first, refresh, then click **Mount read-only**. See
[USB storage](../STORAGE.md) for the full rules, including that a write grant survives app closure.

## First hardware checks

- RESET: stable 800 × 480 display, readable version, working touch controls.
- No card: the keyboard works and storage reports unavailable.
- Card inserted: the USB drive appears read-only; read a file and compare hashes.
- Pair and connect, physically ARM, and type into an editor while the drive is attached; STOP and
  disconnect must still disarm.
- Safely eject, mount read/write, copy a test file and verify its hash. Remount read-only and confirm a
  write is refused.
- A reset returns to read-only and HID. Card insertion and removal require a reset.

An OS eject must reach the SCSI START STOP UNIT callback before a remount is allowed; if it does not,
read-only access is kept.

## Diagnostics

To capture boot output from the UART connector (opening the console can itself reset the board, so open
it first and then switch modes without reopening it):

```bash
.venv-pio/bin/python scripts/watch-waveshare7.py /dev/ttyACM0
```

Press RESET after "Listening" appears. It saves timestamped output under `desktop/logs/` and stops with
Ctrl+C or after 180 seconds. The console is UART0 at 115200.

## Build

```bash
.venv-pio/bin/pio run -e waveshare7
bash scripts/build-release.sh <version> waveshare7
```

Set the version in `src/firmware_version.h` first. Existing release images are immutable; use a new
version for fixes.
