# Roadmap

Plans, not promises. Items move as hardware testing and releases dictate.

## Done

- **Signed releases and online firmware** (0.2.0-dev19): release manifests are signed in CI and the
  app downloads and verifies firmware from published releases.
- **Packaged Linux self-update** (0.2.0-dev20): see [release signing](RELEASE-SIGNING.md) and below.

## Next

- **Self-update for Windows (high priority).** The Windows app runs from Python, so an update would
  download a signed source archive for the release, verify it against the signed manifest, unpack it
  beside the running copy, reuse the existing Python environment unless the dependencies changed (then
  build a new one), and restart into it, with the same rollback as Linux. This needs a source archive
  added to each release's signed manifest and Windows testing first.
- Optional automatic update checks with a quiet install window; today every update is confirmed.

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
