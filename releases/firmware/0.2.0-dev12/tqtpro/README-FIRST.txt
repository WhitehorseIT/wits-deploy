WITS Deploy 0.2.0-dev12 — LILYGO T-QT Pro

Use only this model's image. Dev10 adds a separate Waveshare147 target;
this model retains its existing display and shared keyboard/BLE/update behavior.
All firmware targets were rebuilt and automated tests pass. This snapshot has
not yet been physically retested on the original boards.

Extract the full common firmware ZIP, keeping model folders alongside JSON.
In desktop dev10 use OTA Update for a connected authenticated/disarmed board,
or USB Flash/Update with the exact physical model and serial port. Use native USB.
Safely eject writable SD storage first. Keep power connected until verification.
Working-board USB update preserves bonds by verifying the inactive slot before
committing metadata. Factory install clears settings. Press RESET after USB
verification. A successful update boots PROGRAM; enter HID and reconnect.

Do not assume app0 at 0x10000 is selected after OTA. Use the slot-aware app
rather than the legacy app-only flash-windows helper for updates.

Dev11 rotates only the separate Waveshare147 display/touch UI. This model
retains its display layout; its version label changes to dev11.

Dev12 changes font size only on Waveshare147. This model retains its UI;
its firmware version label changes to dev12.
