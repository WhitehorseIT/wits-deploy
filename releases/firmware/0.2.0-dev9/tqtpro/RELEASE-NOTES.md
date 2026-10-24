# WITS Keyboard firmware 0.2.0-dev9 — pairing countdown redraw

Both T-QT Pro and Waveshare7 now redraw only the countdown text when pairing
seconds change. Fixed-width, opaque text overwrites old digits at 10s -> 9s
without clearing the entire LCD or repainting PIN/buttons/hold bars. A changed
PIN still forces a full redraw. Waveshare also keys the PIN/reconnect state
so reopening the pairing window updates the displayed code immediately.

Firmware only: use controller dev8. GATT UUIDs/layout and OTA protocol are
unchanged from dev8; the existing bond should support this upload directly.
Select this model's .ota.json beside its .app.bin using Update firmware.
Do not use a different model's image. Keep power connected and safely eject
writable SD storage before updating. Native USB resumes in PROGRAM after OTA;
hold HID and reconnect to test pairing countdown, Ping and keyboard output.

User confirmed successful dev8 OTA on both physical boards after app Re-pair
refreshed Linux's old GATT cache. Logs show Waveshare verified in 80.83s and
T-QT Pro in 73.27s. Re-pair is for a changed/stale service database, not a
normal prerequisite for every firmware update.

Safety audit: both layouts contain two OTA app slots. Arduino Update streams
through small buffers into the inactive slot, explicitly rejecting the running
partition. WITS checks length/SHA-256 before Update.end() validates and selects
the new image. A lost connection before commit aborts and leaves the existing
boot selection. No whole-image RAM staging is used. Existing basic-startup
rollback behavior is unchanged; faults after boot confirmation are not covered.
A lost final ACK can happen after commit: inspect the board version.

Validation: both firmware targets build, generated manifests/binaries pass
checksum/image validation. UI changes are pending a physical countdown test.
The unchanged dev8 app previously passed all 89 tests from its extracted ZIP.
Successful OTA transfers do not verify interrupted-transfer recovery, which
still needs a deliberate hardware test. See project OTA-UPDATES.md.

For boards already updated via OTA, use OTA for dev9. Do not blindly write an
app-only serial image to 0x10000: app1 may now be selected. Initial USB bootstrap
from pre-OTA/app0 firmware can use app-only; factory recovery resets selection
and clears bonds. Previous release artifacts remain unchanged.
