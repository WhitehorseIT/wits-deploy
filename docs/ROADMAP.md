# Roadmap

Plans, not promises. Items move as hardware testing and releases dictate.

## Done

- **Check for updates and source self-update** (signed releases and development snapshots, for run-from-source
  installs started with `WINDOWS-START.cmd`): see [release signing](RELEASE-SIGNING.md).
- **Signed releases and online firmware** (0.2.0-dev19): release manifests are signed in CI and the
  app downloads and verifies firmware from published releases.
- **Packaged Linux self-update** (0.2.0-dev20): see [release signing](RELEASE-SIGNING.md) and below.
- **Separate app and firmware releases** (app 0.2.0-dev23, firmware 1.0.0-rc1): see
  [compatibility](COMPATIBILITY.md).

## Next

- Firmware 1.0.0 once the release candidate passes its hardware checks.
- Windows self-update needs testing on real Windows machines (it was built and verified end to end on
  Linux only), and a way to update `WINDOWS-START.cmd` and `apply_update.py` themselves.
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
