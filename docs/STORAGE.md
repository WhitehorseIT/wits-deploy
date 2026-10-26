# USB storage

The Waveshare 7-inch and 1.47-inch boards present their MicroSD card to the computer as a USB drive,
alongside the keyboard. Storage is **read-only by default**; the desktop app grants read/write over the
authenticated Bluetooth link. The T-QT Pro has no card slot and reports storage as unsupported.

## Behavior

- **Read-only is the boot default.** A reset always starts read-only, and write protection is enforced
  in the USB callbacks and SCSI responses, not only by an app setting.
- **The computer owns the drive while it is exported.** The firmware never mounts the same filesystem
  locally. There is no formatting and no automatic repair; use a card reader to prepare a card.
- **Granting read/write** needs an authenticated, disarmed board. From read-only it works on a live
  export without ejecting: a read-only drive holds no unwritten data, so the board withdraws the drive
  for about 3.5 seconds on a timer and presents it again writable.
- **A write grant lasts for the export.** App closure, Bluetooth drops, reconnects and pairing changes
  do not revoke it, because the computer may still hold cached writes. It ends at a confirmed host eject,
  a media error or a reset. Keyboard output still stops and disarms when the control link drops.
- **Read/write back to read-only, and repeating a mode, need a host eject** (a writable drive may hold
  unwritten data). Firmware updates and restarts are blocked while a writable export needs an eject.
- Card insertion and removal require a reset; hot-swap recovery is not implemented.

A successful SD write does not prove the host has flushed its cache, so always eject safely. After an
eject, wait about 1.5 seconds before remounting.

## Performance

USB on the ESP32-S3 is full-speed (12 Mbps), so the practical ceiling is about 1 MB/s. Measured on the
Waveshare 1.47-inch from a Linux host: reads about 0.93 MB/s, writes about 0.42 MB/s. See the
[storage benchmark](STORAGE-BENCHMARK.md) for the method and what was tried.

Use storage for scripts, answer files, drivers and small installers. For large images or bulk
provisioning, fill the card with an ordinary card reader (full speed) and keep Bluetooth as the control
path. High-speed USB would need a chip with a high-speed PHY, which is a different board.

## Implementation notes

- The firmware uses raw sector I/O through the ESP-IDF SD-SPI driver, with one 4 KiB buffer per USB
  callback, bounded read-modify-write for partial sectors, and a background read-ahead task that is
  dropped on any write, eject, mode change, error or restart. I/O failures take the media offline.
- The mass-storage class is created before USB starts, together with the HID keyboard, so one USB
  device carries both.
- An encrypted, authenticated JSON information characteristic reports card presence, capacity, export
  state and access mode, plus optional I/O counters. Older firmware omits it and still works as a
  keyboard. An authenticated opcode remounts the card read-only or read/write and rejects armed or busy
  boards.
- Compile-time C++ tests cover the storage policy (eject, grants, revocation, errors) and the read-ahead
  rules.

Board specifics: [Waveshare 7-inch](boards/WAVESHARE7.md), [Waveshare 1.47-inch](boards/WAVESHARE147.md).

## References

- [Espressif USB device documentation](https://docs.espressif.com/projects/esp-usb/en/latest/esp32s3/usb_device.html)
- [Waveshare 7-inch documentation](https://docs.waveshare.com/ESP32-S3-Touch-LCD-7)
- [Waveshare 1.47-inch documentation](https://docs.waveshare.com/ESP32-S3-Touch-LCD-1.47)
