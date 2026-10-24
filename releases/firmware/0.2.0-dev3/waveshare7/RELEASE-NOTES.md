# Waveshare 0.2.0-dev3 — storage responsiveness and HID controls

The user's dev2 test exposed 30-second USB READ(10) timeouts in the host
kernel log, plus a BLE ping taking about 4.8 seconds. The firmware held one
mutex across SD I/O and status reads; the display and BLE info callbacks
could therefore wait on the card. A remount command was acknowledged, then
a late host eject left media offline while the app incorrectly announced a
successful mount. A second remount subsequently worked. Arming works on the
board; actual keystroke output alongside mass storage remains untested.

Firmware changes:

- Batch aligned sector I/O into an internal DMA buffer up to 4096 bytes
  (8 sectors) rather than issuing a separate SD command for every 512 bytes.
  Preserve bounded read/modify/write for unaligned and partial writes.
- Use the driver's default-speed SD SPI ceiling (20MHz), up from 4MHz.
  Set unused extra SPI pins to -1. Keep an explicit 1000ms command timeout.
- Separate short state snapshots from serialized disk I/O. Display and BLE
  status no longer take the disk mutex. Access changes return busy instead
  of waiting behind a card transaction; revoked grants are checked between
  batches and again before a partial-sector write.
- Require 1.5 seconds since the latest host eject before remounting, to reduce
  collisions with outstanding host eject commands.
- Emit UART I/O error details and five-second activity counters/max transaction
  duration, without logging file contents. These are for measuring the retest;
  improved hardware throughput and resolved USB timeouts are not yet proven.
- Add a fifth touchscreen PROGRAM button, held for 2 seconds. It disarms and
  returns to programming via the existing RGB-safe restart. A writable or busy
  SD drive must be ejected first; idle read-only media is taken offline before
  restart. Restart preparation prevents further remount requests in that boot.
- ARM/DISARM uses amber with dark text; STOP uses white with red text. All
  buttons have a visible border, including on the red armed background.

Desktop app 0.2.0-dev3 verifies exported state/access mode twice after an ACK
before reporting a mount. A late host eject, SD error or revoked access now
produces an explanatory failure. Restart the app to load this behavior.

Validation: both board targets compiled; 72 desktop tests passed from the
extracted the tester app ZIP. Compile-time C++ assertions cover policy transitions,
batched/partial chunk planning and bounds. SHA-256 checks passed. Touchscreen,
card compatibility, transfer throughput and USB timeout behavior need hardware
retesting. Firmware bins from earlier versions remain unchanged.

After safely ejecting the drive, close the UART console and enter FLASH mode.
From the project root:

```bash
.venv-pio/bin/python scripts/flash-waveshare7.py --app-only /dev/ttyACM0
```

The helper now defaults to dev3; app-only preserves the Waveshare partition
layout and bonds. Open the UART watcher before entering HID so opening the
adapter does not interrupt the test. Test a known file's read/write hashes,
eject/remount, responsive STOP/ARM, PROGRAM, and sample typing alongside
storage. Record UART statistics and any host USB timeout messages.

the tester's app-only ZIP is releases/desktop/WITS-Keyboard-App-0.2.0-dev3.zip.
His existing T-QT Pro 0.1.1 remains compatible; no Waveshare image is included
in that ZIP and he does not need a firmware update for this app snapshot.
