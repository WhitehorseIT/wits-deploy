# rc12 — bonded reconnect and larger identity text

- In HID mode, stored bonds enable connectable advertising automatically at
  startup and after disconnects. Computers can scan for the board, but the
  current NimBLE target restricts connections to its saved bond identities.
- Holding left still opens the 60-second window for new PIN pairings. When
  that window expires, bonded-only advertising resumes. Clearing all bonds
  leaves the board offline until a pairing window is opened deliberately.
- Reconnects remain disarmed and show CONNECTING / SAVED / PAIRING during
  authentication instead of asking for a PIN. The four-character ID beneath
  DISARMED is enlarged from scale 1 to scale 3.

Use the app-only image at **0x10000** on an already-working rc9–rc11 board to
keep NVS bonding data. The factory image can overwrite that data.

Validation completed: firmware build, both image checksums, 38 desktop tests,
and ELF/disassembly confirmation that advertising calls pass through the GAP
guard. Hardware/radio validation remains pending. In particular, test private
address reconnection on Windows/Android separately from public-address Linux.

Hardware checks:

1. Keep the existing computer/board bond. Enter HID mode and click Connect in
   the app without holding left; expect authenticated, disarmed and no PIN.
2. Disconnect and Connect again; then close/reopen the app and repeat.
3. Confirm a new/unbonded computer cannot pair until left opens the PIN window.
4. Open that window and confirm a new PIN pairing still works.
5. Clear bonds: expect the success notice, no automatic pairing, and no saved
   reconnect until another physical PIN pairing is completed.
6. Check the larger ID fits above the progress bars/button labels.

Implementation note: `platformio.ini` wraps `ble_gap_adv_start` to forward the
framework's callback through a pairing-policy guard. The framework's normal
repeat-pairing callback deletes an existing bond; the guard rejects that path
outside a physically authorized pairing attempt. Keep the linker flag and
wrapper together when changing the BLE framework. The advertising accept-list
implementation is for the current NimBLE target; other stacks retain the old
physical-window behavior until explicitly ported.
