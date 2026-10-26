# Compatibility

What the firmware and the app promise each other, so boards already in the field keep working with
future apps and the reverse. These rules apply to the firmware 1.x series.

## Versions

- The **firmware** and the **desktop app** have separate versions and separate releases. Firmware
  releases are tagged `fw-v<version>` and carry the firmware ZIP; app releases are tagged `v<version>`
  and carry the app. The app bundles one firmware release and can download newer ones.
- Firmware uses semantic versioning from 1.0.0: a patch release fixes bugs, a minor release adds
  features without breaking anything below, and a major release may need a USB (factory) install.
- Every 1.x firmware release uses the same release manifest format, so the app must always be able to
  update 1.x boards from a downloaded firmware ZIP. A firmware release is cut only when the firmware
  code changes.

## Frozen for 1.x

- **Bluetooth protocol version 2.** Service `62fa47a0-d77c-4045-9e7e-81d5a93931cc` with RX
  `2bcd9577-d0b1-4164-9ff4-88f0cc29cbc3`, TX `7cb2a248-dad7-4149-a36f-fc2dfe91675d` and the information
  characteristic `3abfae15-ec3c-49db-a65d-17c8d977c102`. Existing opcodes (ping 0x01, type text 0x10,
  stop 0x11, key action 0x12, identify 0x13, key interval 0x14, storage mode 0x15) keep their meaning.
  New opcodes and new optional fields may be added; a board or app that does not know one must ignore
  it. A protocol version mismatch is refused, never guessed at.
- **Board model codes** for Bluetooth updates: Waveshare 7-inch = 1, T-QT Pro = 2, Waveshare 1.47-inch = 3,
  with the firmware targets `waveshare7`, `tqtpro` and `waveshare147`.
- **Partition layouts.** Each model keeps its flash layout: T-QT Pro `ota_nofs_4MB`, Waveshare 7-inch
  `default_8MB`, Waveshare 1.47-inch `default_16MB` (from the Arduino ESP32 core), with two OTA app
  slots and the OTA selection metadata. Changing a layout means a USB factory install, so it needs a
  major version.
- **Pairings survive updates.** Bluetooth and USB working-board updates keep stored bonds; a factory
  install clears them.
- **Storage rules:** read-only after every reset, write protection enforced by the board, and a write
  grant that lasts until a host eject, a media error or a reset (see [USB storage](STORAGE.md)).
- **Updates** only ever write the inactive app slot and verify it before changing the boot selection;
  an interrupted update leaves the previous firmware bootable.

## Release manifests

Signed manifests are schema 1 with a `kind` of `app`, `firmware` or `source` (a development snapshot, which also
carries the `commit` and a growing `sequence`). Fields may be added, and apps
ignore fields and file labels they do not know. A release must not add a new file label while older
apps that would reject it still need to update to that release (see
[release signing](RELEASE-SIGNING.md#manifest-compatibility)). Signing keys rotate through the manifest's
`add_keys`.

## What can change in a minor version

New board models, new optional information fields, new opcodes, new on-screen features, and faster
transfers. None of these may stop an older app from controlling or updating a board.
