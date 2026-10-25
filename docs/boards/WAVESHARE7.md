# Waveshare ESP32-S3-Touch-LCD-7 Ver1.1 prototype

Target: `waveshare7`, latest firmware `0.2.0-dev9`, controller `0.2.0-dev8`. The existing T-QT Pro
remains the default build target. This is a new hardware bring-up, separate
from the stable 0.1.0 distribution and T-QT Pro 0.1.1 display update.

User's initial flash succeeded on 2026-10-23. Esptool confirmed ESP32-S3
revision v0.2, **8 MB quad flash, 8 MB PSRAM** and a verified write of the
factory image. User confirmed the WITS programming screen and touchscreen
controls work. Initial HID switching returned to programming, both with a
card and without one; UART showed RTC watchdog resets. User later entered
HID successfully with a different card. Opening UART also resets the board;
keep the console open across the test. FLASH transfer works from PROGRAM.
Dev2 hardware retest succeeded with both cables connected: the user confirmed
USB mass storage works. Capture `desktop/logs/waveshare-uart-20261023-221826-599789.log`
shows RGB cleanup completing, RTC_SW_CPU_RST / reset_reason=3 selecting HID+MSC,
SD probing succeeding in about 68 ms, and USB/display/BLE reaching Startup
complete at 878 ms with 149728 bytes internal heap free. No watchdog reset
appears in that run. Read-only enforcement, actual HID typing alongside storage,
app-controlled eject/remount/write grants and repeated/card-specific reliability
still need hardware checks. This run does not isolate the cause of prior resets.
Dev2 adds RGB cleanup before restart and UART stage tracing; see its release
notes. Existing dev images remain unchanged.

Dev3 is built and ready for hardware retest. It adds PROGRAM (hold 2 seconds),
amber ARM/DISARM and white/red STOP, 20MHz batched SD transfers, status reads
independent of disk I/O, UART performance/error counters and confirmed remount
feedback in the app. The changes address blocking paths found after dev2's
30-second host read timeouts; hardware throughput/reliability is unverified.

User's dev3 retest confirmed typing works and access is much better. A spinning
eject showed a pending UDisks unmount job with active writeback (~480 KiB/s in
the diagnostic sample); let writes drain before resetting. Dev8 additionally
adds SCSI flush handling and app-managed BLE OTA without changing the computer's
Wi-Fi network. See OTA-UPDATES.md. Dev8 BLE OTA was verified in 80.83 seconds after Linux Re-pair refreshed its
GATT cache. Dev9 fixes full-screen pairing-countdown redraws; physical display
verification and interrupted-transfer recovery tests are pending.

## Capturing the HID startup failure

The user's current connection is the **UART** connector (CH343 USB serial,
host journal VID:PID 1a86:55d3, ttyACM0), suitable for flashing and boot/panic
output. The separate **USB** connector carries native HID/MSC to the target
PC. Absence of that native USB cable should not itself reset the firmware.

```bash
.venv-pio/bin/python scripts/watch-waveshare7.py /dev/ttyACM0
```

After Listening appears, press RESET, then hold the touchscreen HID control.
Ctrl+C stops the capture (otherwise it runs 180 seconds). It saves timestamped
output under `desktop/logs/waveshare-uart-*.log`. It requests inactive DTR/RTS,
but the adapter/OS may still pulse reset during port opening. Open the console
first, then switch modes without reopening it. The SDK console/panic output
is UART0 at 115200. Direct serial access
is hidden from the agent's sandbox, but the shared log can be read afterward.

## Flash and start

From the project root, with the Waveshare in ROM bootloader mode:

```bash
.venv-pio/bin/python scripts/flash-waveshare7.py
```

With multiple serial adapters, supply the board's port explicitly:

```bash
.venv-pio/bin/python scripts/flash-waveshare7.py /dev/ttyACM0
```

For the initial dev3/app0 bootstrap, add `--app-only` to preserve bonds.
After OTA, use OTA again or follow active-slot recovery in OTA-UPDATES.md.
The helper defaults to dev9; use `--version 0.2.0-dev` to select the initial
prototype explicitly. It verifies the image SHA-256 and checks for an ESP32-S3 with at least
8 MB flash before writing. It keeps the probe in bootloader mode between
checking and uploading. It uses the Waveshare-specific factory image under
`releases/firmware/0.2.0-dev9/waveshare7/` at 0x0 (initial app-only at 0x10000).

Press RESET after flashing. Expect a blue WITS programming screen with
firmware version. Insert a preloaded MicroSD before entering HID mode. Hold
the touchscreen HID control for two seconds; it reboots into simultaneous
keyboard and read-only mass storage. Use the **native USB** port for these
interfaces, rather than the USB-to-UART connector.

Touch controls in HID mode: hold PAIR for 2 seconds, STOP immediately, tap
ARM/DISARM after authentication, or hold CLEAR for 5 seconds to clear bonds.
Dev3 also has PROGRAM held for 2 seconds; safely eject writable storage first.
PAIR/CLEAR/FLASH/HID show hold progress. Pairing PIN remains readable onscreen.
RESET returns to programming mode; FLASH enters ROM download mode.

## Desktop storage controls

```bash
cd desktop
.venv/bin/python run.py
```

Pair/connect through the existing flow. Highlight exactly one device row;
storage controls operate on that row independently of the keyboard Target
checkboxes. Storage status reports the board firmware version, card capacity
and access mode. T-QT Pro boards report unsupported; older firmware has no
optional information characteristic but still works as a keyboard.

To enable writes (firmware 0.2.0-dev15 and newer):

1. Disarm the board.
2. Click Mount read/write. The board briefly withdraws the drive, then presents
   it again writable, so the computer re-detects it a few seconds later. No eject
   is needed, because a read-only drive holds no unwritten data.

With older firmware, safely eject the SD drive on the deployment PC first,
click Storage status (the board reports ejected), then click Mount read/write.

To restore read-only access, safely eject first (a writable drive may hold
unwritten data), refresh and click Mount read-only.
No automatic filesystem format or local filesystem mount occurs. BLE is the
control path; copy installer files through USB or a separate card reader.

With dev13, a granted R/W export remains writable across BLE disconnect,
new connections, pairing and app closure until confirmed host safe eject.
Reboot starts read-only. Older firmware revoked writes on BLE changes and
could interrupt a copy. Eject is still required before remount/restart/OTA.

## First hardware checks

- RESET: stable 800x480 display, readable version and working touch controls.
- No card: keyboard still operates; storage reports unavailable.
- Preloaded card: USB drive appears read-only; read a file and compare hashes.
- Pair/connect, physically ARM, and type into an editor while the drive is
  attached; verify STOP and disconnect still disarm.
- Safely eject, refresh, mount read/write, copy a test file and verify its hash.
  Eject/remount read-only and verify a write is refused.
- App disconnect/reconnect must preserve R/W during a copy; reboot resets to read-only. Reboot requires entering HID
  again. Card insertion/removal requires reset; hot-swap recovery is not implemented.

An OS eject must reach the SCSI START STOP UNIT callback before remount is
allowed. Wait at least 1.5 seconds after eject before requesting a remount.
If it does not, retain read-only access and report the OS/eject
behavior for debugging; the app does not bypass that requirement.

## Implementation and verification

- Manufacturer base-model pins: RGB LCD on GPIO0/1/2/3/5/7/10/14/17/18/21/
  38/39/40/41/42/45/46/47/48; GT911 touch over I2C SDA8/SCL9 with IRQ4.
  CH422G controls TP_RST1, backlight2, LCD_RST3, SD_CS4 and USB_SEL5.
- SD SPI: MOSI11, SCK12, MISO13, dedicated bus with expander CS held low,
  matching the vendor example. Raw IDF sector I/O avoids mounting FAT locally.
- 8MB partition layout and octal 8MB PSRAM; RGB clock 16MHz and bounce buffer.
  Dev3 SD uses up to 20MHz and batches up to eight sectors per transaction.
- MSC is constructed before USB.begin() alongside HID. Default write protection
  is advertised via MSC and checked again in the write callback. Partial-sector
  transfers use bounded read/modify/write; I/O failures take media offline.
- Encrypted MITM-protected JSON info characteristic:
  `3abfae15-ec3c-49db-a65d-17c8d977c102`, schema1. Existing v2 notifications
  remain 5 bytes. Authenticated opcode0x15 accepts one boolean byte to remount
  an ejected card read-only (0) or read/write (1); rejects armed/busy boards.
- Both targets compiled; 68 desktop tests passed, including UI target selection
  and permission gating. Compile-time C++ policy assertions cover eject,
  read/write grants, revocation and error transitions. Hardware is not validated
  by those checks.

Build a new artifact with `bash scripts/build-release.sh VERSION waveshare7`
after updating `src/firmware_version.h`. Existing release images are immutable;
use a new development version for fixes. The flash helper defaults to dev9
and also accepts an explicit `--version`.

Manufacturer references (base-model code, not a claim of physical validation):

- https://docs.waveshare.com/ESP32-S3-Touch-LCD-7
- https://github.com/waveshareteam/ESP32-S3-Touch-LCD-7/tree/bc51a84b30c0cea018fee6e0d7427ec10102060e/examples/Arduino/examples/03_SD_Test
- https://github.com/waveshareteam/ESP32-S3-Touch-LCD-7/blob/bc51a84b30c0cea018fee6e0d7427ec10102060e/examples/Arduino/libraries/ESP32_Display_Panel/src/board/supported/waveshare/BOARD_WAVESHARE_ESP32_S3_TOUCH_LCD_7.h

The currently published schematic is marked V1.2; this port uses the shared
base-model example wiring and awaits testing on the user's Ver1.1 board.
