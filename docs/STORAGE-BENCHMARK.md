# USB storage throughput: benchmark plan

Status: plan only. No firmware changes have been made for it yet.

## Why

On the Waveshare ESP32-S3-Touch-LCD-1.47 (dev13), measured from a Linux host with a 29.8 GiB exFAT card:

| Measurement | Result |
| --- | --- |
| Sustained write, 64 MiB file | about 0.47 MB/s (earlier run about 0.16 MB/s while the host was also draining a large cache) |
| Cold-cache read of the same file | about 0.37 MB/s (2 min 54 s for 64 MiB) |
| USB link negotiated | 12 Mbps, full-speed |

Full-speed USB mass storage tops out at roughly 1 MB/s, so the measured rates leave room. The ESP32-S3
has no high-speed USB, so the ceiling cannot be raised by software.

## What the code does today

From `src/usb_storage.cpp`, `src/storage_transfer.h`:

- SD card on SPI2 in SPI mode, `max_freq_khz = SDMMC_FREQ_DEFAULT` (20 MHz).
- On the 1.47 board the card uses GPIO 14 (CS), 15 (MOSI), 16 (SCK), 17 (MISO). Those are not the chip's
  direct SPI2 pins (10 to 13), so the signals go through the GPIO matrix, which limits reliable clocks.
  The 7-inch board uses pins 11, 12, 13 and may behave differently.
- Every USB read or write callback takes a mutex, checks policy, then moves data through one 4096-byte
  DMA buffer, so at most 8 sectors per SD command (`IO_BUFFER_BYTES = 4096`). Writes are synchronous.
- Partial sectors do a read-modify-write.
- The firmware counts requests, bytes and the slowest request but only prints them to a UART that the
  1.47 board does not expose.
- Non-read/write SCSI commands print two lines each to the UART (`genericScsi`).

## Hypotheses, most likely first

1. **Request size.** If TinyUSB hands the callback 512 bytes at a time, every sector costs a separate SD
   command. Check: average bytes per request from the firmware counters.
2. **SD command overhead.** Many small multi-block writes each pay setup and card busy time. Check: time
   spent inside the SD calls versus total time, and the effect of larger batches.
3. **Card behavior.** Some cards take several milliseconds per write in SPI mode, and partition or
   cluster misalignment forces read-modify-write inside the card. Check: partition start sector, cluster
   size, a second card.
4. **SPI clock.** Probably not the main lever on the 1.47 board (GPIO matrix). Try 26 MHz only if the other
   items leave a gap, and only if reads stay error-free.
5. **USB ceiling.** Full-speed bulk with 64-byte packets limits the ceiling to roughly 0.9 to 1.0 MB/s.
   Measure the raw read rate to see how close the SD side gets to it.

## Phase 0: baselines from the host (no firmware change)

Run `scripts/storage-benchmark.sh` with the board's volume mounted read/write:

- Raw read, non-destructive, direct I/O, at 4 KiB, 64 KiB and 512 KiB block sizes. This separates request
  size sensitivity from filesystem effects.
- File write, 32 MiB random data, `conv=fsync`, timed to the end of the flush. Drop the file's cache
  afterwards.
- File read, same file, cold cache.
- Record partition start sector and cluster size (`/sys/block/sda/sda1/start`, `fsck.exfat -n`).

Always use a file big enough to outlast host caching, and watch `Dirty` in `/proc/meminfo` reach zero
before judging a number. Delete test files with Shift+Delete, not the file manager's Trash.

## Phase 1: instrument the firmware

Add storage counters to the BLE board-info JSON the app already reads, so no UART is needed:

- read and write request counts, total bytes, largest request, average bytes per request
- microseconds spent inside the SD read and write calls versus total callback time
- slowest single request, I/O error count

Show them in the app's Storage status line. Counters reset on demand. Everything is read-only
information. This is a small, low-risk change.

## Phase 2: one experiment at a time

For each, build, flash over Bluetooth, repeat the Phase 0 file tests three times, and compare:

| Experiment | Change | Safety check afterwards |
| --- | --- | --- |
| A | Remove per-command UART printing from the hot path | storage policy tests |
| B | Larger SD batches (16 KiB, 32 KiB) if request size allows | partial-sector and boundary tests |
| C | Pre-erase hint before long writes if the card honors it | integrity hash |
| D | 26 MHz SPI clock | 100 MiB read hash, no CRC errors |
| E | Second card (different brand or class) | same tests |

Keep a change only if it is faster in all three runs and every safety check passes.

## Acceptance

- Sustained cold-cache read of a 64 MiB file: at least 0.8 MB/s.
- Sustained write of 64 MiB, flushed: at least 0.6 MB/s.
- SHA-256 of the copy matches the source after an eject and remount.
- A copy completes with the desktop app closed (dev13 behavior preserved).
- `tests/storage_policy_test.cpp` and the other compile-time checks still pass.
- Windows gives similar numbers (it may use different request sizes).

## Out of scope

High-speed USB (480 Mbps) would need a chip with a high-speed PHY, such as the ESP32-P4. That is a
different board and a different project.
