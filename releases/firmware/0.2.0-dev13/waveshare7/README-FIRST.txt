WITS Deploy firmware 0.2.0-dev13 — waveshare7

Dev13 fixes writable USB storage on the two Waveshare models: closing the app,
losing/re-establishing BLE, pairing or clearing bonds no longer write-protects
a mounted R/W export. A grant lasts until confirmed USB host eject. Boot/reset
still starts read-only. Keyboard output stops and disarms on BLE disconnect.
T-QT Pro has no SD storage; its existing keyboard behavior is retained.

Use only the image for the exact physical model. The common release JSON is
one level above this model folder and serves all three board types. In your
existing app, safely eject writable storage on its USB host, leave the board
disarmed, select OTA Update and choose the common dev13 JSON. Keep power on.
After verification, enter HID again. App dev13 adds an independent Auto-connect
checkbox per saved device; older apps can install the firmware manually.

USB Flash/Update supports inactive-slot updates that preserve pairings and
factory installation that clears them. Enter FLASH first, choose the physical
model and correct port. Waveshare7 uses UART; Waveshare147 and T-QT Pro use
native USB. Press RESET after verification. Do not assume app0 at 0x10000 is
the selected slot after OTA. Keep all model folders alongside the common JSON.

All targets compile and simulated tests pass. The storage copy/disconnect/
reconnect/eject behavior and automatic reconnect still need real device tests.
Previously interrupted copies may be incomplete; verify against their sources.
