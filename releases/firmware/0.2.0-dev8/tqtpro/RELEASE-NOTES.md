# WITS Keyboard 0.2.0-dev8 — Bluetooth OTA

Development release for T-QT Pro and ESP32-S3-Touch-LCD-7 Ver1.1. Both model
images include OTA over the existing paired, MITM-authenticated BLE connection.
The PC keeps normal internet access. The undistributed dev4-dev7 Wi-Fi drafts
are superseded; no hotspot or separate Wi-Fi password is used.

Each existing board needs one initial USB bootstrap. After that, highlight
one connected/disarmed board in the dev8 desktop app, choose Update firmware,
and select the matching .ota.json beside its .app.bin. Images are model-specific,
not unit-specific. Never flash the other model. See project OTA-UPDATES.md.

Transfer uses bounded queues and four-packet windows, matching the negotiated
write size. Device acknowledgments represent accepted writer data. Full length,
SHA-256 and ESP image validation are required before inactive-slot boot selection.
Keyboard activity is blocked during transfer. Waveshare quiesces storage and
stops RGB DMA before flash writes; T-QT Pro shows a static update screen.

Cancel/disconnect/timeout before commit aborts the update and retains the boot
selection. A paused Waveshare display stays dark until restart. Losing the
final acknowledgment may happen after commit; check the board version before
retrying. The SDK supports rollback, but confirmation tests only essential IO,
USB and PSRAM startup before display initialization, not full app functionality.
Do not assume every later application fault will trigger automatic rollback.

Also includes Waveshare SCSI SYNCHRONIZE CACHE(10/16), correct signed generic
SCSI failures and flush/eject UART logging. The recorded host-eject requirement
survives revocation of a writable grant. A dev3 eject spinner was observed doing
actual host writeback (~480 KiB/s); that work must finish before reset. SCSI
handling is a separate robustness fix, not a proven cause of that spinner.

Validation: both firmware targets build; 89 desktop tests pass; compile-time
C++ storage policy/transfer/SCSI assertions pass. Generated images/manifests and
app archive checksums are checked. BLE OTA transfer speed, interrupted transfer,
both slot boots, post-update HID, and the new SCSI path await hardware testing.
User confirmed typing and improved storage access on earlier Waveshare dev3;
The tester confirmed older app/firmware keyboard operation on Windows.

Initial USB app-only flashing assumes existing app0 is selected (user dev3 and
The tester 0.1.1). Once OTA selects app1, writing 0x10000 alone does not select app0.
Use OTA thereafter, or account for active slot/use factory recovery, which
clears bonds. Stable releases and already distributed artifacts are unchanged.
