# USB storage throughput: benchmark plan

Status: Phase 1 instrumentation is implemented (firmware counters, the optional `io` block in the board
information, and a throughput line in the app's Storage status). Phase 2 experiments are not started.

Decision (2026-10-24): keep USB storage for small files and tighten its speed; large images are out of
scope for this hardware.

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

## Baseline, firmware 0.2.0-dev15, Waveshare 1.47, Linux host (2026-10-25)

`scripts/storage-benchmark.sh`, 32 MiB random file, exFAT card, USB 12 Mbps:

| Measurement | Result |
| --- | --- |
| Write, flushed to the card | 0.42 MB/s (32 MiB in 75.3 s) |
| Read, cold cache | 0.51 MB/s (32 MiB in 62.9 s) |
| Readback | matches the source |
| Partition start sector | 2048 (1 MiB aligned) |

What the numbers show:

- **Alignment is fine.** A 2048-sector start is 1 MiB aligned, so hypothesis 3's partition-misalignment
  case is unlikely.
- **The host sends large requests.** Linux issued writes averaging 99.6 KiB and reads averaging 75.6 KiB
  (block layer limit 120 KiB, 2 requests queued).
- **The firmware handles them 4 KiB at a time.** The largest callback the board ever saw was 4096
  bytes, so each host request becomes about 25 separate callbacks, each with its own SD command.
  (This refutes the 512-byte-callback worry from hypothesis 1: callbacks are 4 KiB.)
- **Per 4 KiB callback:** write about 9.2 ms and read about 7.7 ms (8192 callbacks in the run).
  On reads, the board counters showed about 3.4 ms inside the SD card per callback (99% of callback
  time) and a 4 KiB USB transfer takes about 3.4 ms at full speed. The two happen one after the other,
  not overlapped, which fits the measured 0.51 MB/s. Writes spend the rest of their 9.2 ms on SD
  programming time, paid again for every 4 KiB.
- **Where the gain is:** read larger blocks from the card at once and overlap them with USB, and write
  larger runs per SD command. Both amortize per-command cost. Reads can go first because they are
  safe: they only add a read-ahead buffer that is thrown away on any write, eject or media change.

## Phase 1: instrument the firmware (done)

Add storage counters to the BLE board-info JSON the app already reads, so no UART is needed:

- read and write request counts, total bytes, largest request, average bytes per request
- microseconds spent inside the SD read and write calls versus total callback time
- slowest single request, I/O error count

Show them in the app's Storage status line. The counters only count up while the board runs; the app
reports the difference between two refreshes ("Since last refresh: write 0.47 MB/s while busy, avg 4.0
KiB per request, 90% in the SD card"). Everything is read-only information. The worst-case board
information message is 437 bytes against the app's 512-byte limit, and boards on older firmware simply
omit the block.

How to use it: press **Storage status** before a copy, run the copy, then press it again.

## Phase 2: one experiment at a time

For each, build, flash over Bluetooth, repeat the Phase 0 file tests three times, and compare:

| Experiment | Change | Safety check afterwards |
| --- | --- | --- |
| A | Remove per-command UART printing from the hot path. Skipped: the prints are only on non-read/write SCSI commands (flush, start/stop), not in the read/write path, so removing them gains nothing | n/a |
| B1 | Read-ahead: fetch 32 KiB from the card on a sequential read and serve the next callbacks from RAM; discard on write, eject or media change (expected: reads toward 0.8 MB/s) | partial-sector and boundary tests, cold-cache hash |
| B2 | Larger write runs per SD command. Needs a short write-behind buffer, which changes the current rule of no application write cache: flush it before any read, SYNCHRONIZE CACHE, eject, mode change or restart, and on a short timer. Decide deliberately before doing this | storage policy tests, eject and unplug tests, hash after eject |
| C | Pre-erase hint before long writes if the card honors it | integrity hash |
| D | 26 MHz SPI clock | 100 MiB read hash, no CRC errors |
| E | Second card (different brand or class) | same tests |

Keep a change only if it is faster in all three runs and every safety check passes.

## Experiment log

| Build | Change | Result |
| --- | --- | --- |
| dev15 | baseline (see above) | write 0.42 MB/s, read 0.51 MB/s |
| dev16 | B1 read-ahead: a sequential read triggers one 32 KiB card read, the next callbacks are served from RAM; the window is dropped on any write, eject, mode change, error or restart (compile-time tests in `tests/storage_policy_test.cpp`) | Measured 2026-10-25: read 0.58 MB/s (54.7 s for 32 MiB, was 62.9 s), write 0.42 MB/s unchanged (75.3 s), readback matches. Read gain is 14%, below the 45% predicted |

Why the read gain was small: per 4 KiB callback the read took 6.7 ms (was 7.7 ms). A 4 KiB USB transfer at
full speed takes about 3.4 ms, so about 3.3 ms per callback is still the SD card. That fits roughly 22 ms
to fetch a 32 KiB window (64 separate 512-byte block transactions in the ESP-IDF SD-SPI driver, about
0.35 ms each, a raw SD read rate near 1.4 MB/s) and means the card read and the USB transfer still happen
one after the other. The remaining read gain is from overlapping them: prefetch the next window from a
background task while USB sends the current one (double buffer, reads only).

Writes cannot overlap the same way without a write-behind buffer, because TinyUSB does not accept the
next 4 KiB until the write callback returns. That is the deliberate no-write-cache rule; changing it is
the user's decision. The product's main flow is reading installers from the board on target machines, and
the card can be filled with an ordinary card reader at full speed, so read speed matters most.
| dev17 | B3 overlap: a background task reads the next 4 KiB from the card while USB sends the current piece (replaces the 32 KiB window; same lock, a generation counter drops it on any write, eject, mode change, error or restart; compile-time tests) | Measured 2026-10-25: read **0.93 MB/s** (34.6 s for 32 MiB; was 62.9 s at dev15, 54.7 s at dev16), write 0.42 MB/s unchanged (75.9 s), readback matches. Reads are now within a few percent of the practical full-speed USB limit (about 1 MB/s) |

Result against the acceptance targets: reads pass (0.93 vs 0.8 MB/s). Writes (0.42 vs 0.6 MB/s) do
not, and stay that way by choice: improving them needs a write-behind buffer, which breaks the
no-write-cache rule, and the card can be filled with an ordinary card reader at full speed. Revisit only
if loading files through the board itself becomes a real workflow.

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
