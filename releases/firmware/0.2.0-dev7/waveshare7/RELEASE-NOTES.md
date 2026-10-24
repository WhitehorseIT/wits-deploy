**Superseded, unshipped hotspot draft. Use dev8 Bluetooth OTA instead.**

# Waveshare 0.2.0-dev7 — hotspot updater and storage flush handling

Adds a two-second UPDATE touchscreen action in PROGRAM/HID, a separate
password-protected AP session, and the Python controller's Update firmware
dialog. See OTA-UPDATES.md for setup, first serial bootstrap and later uploads.
The app validates a generated `.ota.json` and matching app image; the board
checks target/size/SHA-256 and ESP image validity before selecting the inactive
slot. The session expires, uses RAM-only random credentials and starts no BLE
or HID/storage interface. RGB stops before flash writes. Essential startup
checks confirm a new OTA image before RGB starts; failed checks request the
SDK's configured rollback. Full application correctness is not inferred from
that startup confirmation.

Also adds SYNCHRONIZE CACHE(10/16) handling with synchronous write completion
and SD status checks, properly signed failures for unsupported SCSI commands,
and UART traces for flush/start/stop/eject. A Waveshare-only linker wrapper
replaces the Arduino generic SCSI callback; retain its flag with the code.
`needsEject` remains set after a writable grant is revoked, preventing software
restart/update from bypassing unfinished host writes.

Host diagnostic findings: user confirmed dev3 typing works and storage is much
improved. A spinning eject was a pending UDisks filesystem-unmount job. At
23:04:30 its mount path was already absent, but disk counters still advanced
by 960 written sectors in roughly one second (~480 KiB/s) with two outstanding
partition requests. This is real pending writeback. It must finish before
resetting/flashing; generic SCSI flush support is a separate robustness fix,
not an established cause of that spinner. The diagnostic script reads state
and saves logs without opening/resetting UART.

Validation: 82 desktop tests pass; both firmware targets compile; C++ policy,
chunk and SCSI protocol assertions pass. SHA checks and actual generated-image
manifest validation pass. Real AP/update/eject behavior still needs hardware
retesting. Internal dev4-dev6 builds were superseded before distribution; use
dev7. Existing dev3 and the tester's dev3 app archive remain unchanged.
