# Roadmap

Plans, not promises. Items move as hardware testing and releases dictate.

## Next test build

- **Signed releases.** Release manifests and firmware images are signed in CI with an Ed25519 key;
  the app and (later) tools verify them against a public key built into the app.
- **Online firmware.** The desktop app fetches firmware for each board model from published
  releases instead of requiring a bundled copy, keeping the bundled set as an offline baseline.
- **Desktop self-update.** The app downloads a verified update and restarts itself.

## Platforms

- **Windows:** run the app from Python (no signed installer or bundled executable needed); a
  one-step installer and updater is planned. Native Windows testing is still pending.
- **Linux:** packaged build and source install both supported.
- **Android and iOS** controllers. iOS requires an Apple developer account.

## Web interface

A browser-based controller built on Web Bluetooth. Browser support is the limit: Web Bluetooth
works in Chromium-based browsers on desktop and Android, and not in Firefox, Safari or any iOS
browser, and individual operating systems add their own restrictions. It would complement the
desktop app rather than replace it. The existing `web/` folder is an early keyboard-only prototype.

## Other ideas

- Pair a board over Bluetooth as a keyboard as well as a controlled device.
- Larger or faster USB storage needs different hardware (high-speed USB); see
  [the storage benchmark](STORAGE-BENCHMARK.md).
