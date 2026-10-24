# Waveshare 0.2.0-dev2 — startup diagnostics and RGB reboot cleanup

Observed on dev: programming screen/touch work; initial HID mode switches
returned to programming with or without a card. UART captures showed
RTCWDT_RTC_RST and no panic trace. User subsequently reached HID mode using
a different MicroSD, and found opening UART reset the board. FLASH from the
programming touchscreen worked. Root cause remains unconfirmed; card changes
and serial-port opening are confounding factors in the earlier observations.

This build:

- Prints firmware/reset reason/requested mode and startup-stage markers
  directly to UART0, including internal free heap. Covers board IO, HID/MSC,
  SD host/card probe, native USB, RGB display and BLE. No PIN/payload logging.
- Deletes the active RGB panel through IDF's public API before HID/FLASH
  restarts, while caches and the scheduler are available. Captures the GFX
  library's otherwise private panel handle through a linker wrapper, without
  altering the installed dependency or depending on private struct layouts.
  Failure to delete cancels the requested restart; freed display memory is
  never rendered again in that boot.
- Keeps the existing reset policy: only an explicit software restart with
  the one-shot RTC magic selects HID; a watchdog or physical reset returns
  to programming. SD and write-protection behavior are unchanged.

RGB cleanup is a proposed fix for a potential restart/cache interaction, not
an established explanation for the captured RTC watchdog reset. Test this
build with the console opened first and kept open throughout the mode switch.
The UART adapter/Linux driver may pulse reset during serial-port opening even
though the capture helper requests inactive DTR/RTS.

Verification: both board targets compile, 68 desktop tests pass, image SHA-256
checks pass, and ELF disassembly confirms RGB creation reaches the wrapper and
both restart paths call display cleanup. Actual restart/SD behavior awaits
user hardware testing. App stays 0.2.0-dev; no app update needed for tracing.

Hardware update (2026-10-23): user confirmed mass storage works with both
USB cables connected. UART capture 221826-599789 shows RGB cleanup, a normal
RTC_SW_CPU_RST into HID+MSC, SD card ready, and USB/display/BLE startup complete
at 878 ms (149728 bytes internal heap free). No watchdog reset in this run.
Read-only enforcement, actual HID typing with storage attached, write-access
changes and repeated/card-specific reliability remain unverified. This does
not prove a single root cause for the original resets.

Upgrade from the existing Waveshare dev prototype with:

```bash
.venv-pio/bin/python scripts/flash-waveshare7.py --app-only /dev/ttyACM0
```

Close any serial console first and enter ROM FLASH mode. App-only writes at
0x10000, preserving bonds and the already-installed 8MB Waveshare partition
layout. After upload, run the UART watcher, RESET if needed, then hold HID
with the watcher still open. Inspect the last WITS stage and reset reason.
