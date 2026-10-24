WITS Deploy 0.2.0-dev10 — Waveshare ESP32-S3-Touch-LCD-7 Ver1.1

Use only this model's image. Dev10 adds a separate Waveshare147 target;
this model retains its existing display and shared keyboard/BLE/update behavior.
All firmware targets were rebuilt and automated tests pass. This snapshot has
not yet been physically retested on the original boards.

Extract the full common firmware ZIP, keeping model folders alongside JSON.
In desktop dev10 use OTA Update for a connected authenticated/disarmed board,
or USB Flash/Update with the exact physical model and serial port. Use UART for flashing; separate USB for HID/storage.
Safely eject writable SD storage first. Keep power connected until verification.
Working-board USB update preserves bonds by verifying the inactive slot before
committing metadata. Factory install clears settings. Press RESET after USB
verification. A successful update boots PROGRAM; enter HID and reconnect.

Do not assume app0 at 0x10000 is selected after OTA. Use the slot-aware app
rather than the legacy app-only flash-windows helper for updates.
