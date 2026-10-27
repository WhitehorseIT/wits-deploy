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

## Related projects and ideas to borrow

Other people are solving nearby problems. These notes are descriptions of their public pages, not tests of their
work; check their own documentation and licenses before relying on anything here.

- [Openterface KeyMod](https://www.crowdsupply.com/techxartisan/openterface-keymod) is a commercial USB dongle that
  a phone controls over Bluetooth Low Energy (companion app for Android and iOS) as a keyboard, mouse, gamepad
  and SSH link. It is a phone-first tool for controlling one machine; this project is desktop-first, controls
  several boards and shares files from an SD card. Its app is announced as open source after its campaign.
- [bluetooth-to-keyboard-input-esp32-s3-zero](https://github.com/ArtiomSu/bluetooth-to-keyboard-input-esp32-s3-zero)
  is an ESP32-S3 Bluetooth-to-USB keyboard with Python desktop tools and an Android app, released under the
  GPL-3.0. It adds an application-level encryption layer and flashes from a browser.

Ideas worth considering, written as ideas only (this project is MIT licensed, so code from GPL projects must not be
copied in; reading their documentation for ideas is fine):

- **Keyboard layouts.** Typing assumes a US layout. A target-layout setting would make text come out right on
  non-US computers.
- **Replay protection.** Commands rely on the Bluetooth link's own encryption. A counter checked by the board
  would make a captured command useless; it could arrive as an additive part of a later protocol version.
- **First install from a browser.** A browser-based flasher would give beginners a no-install first flash,
  alongside the app's USB flasher.
- **Mouse input and a phone app,** which the Android and iOS item above already covers.
