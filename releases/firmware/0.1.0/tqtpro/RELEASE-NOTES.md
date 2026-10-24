# WITS Keyboard 0.1.0

First stable release, promoted from the user-tested rc13 firmware on
2026-10-23. Both firmware images are copied byte-for-byte from rc13, rather
than rebuilt. Existing rc13 boards do not need reflashing.

## Included

- Native Python Windows/Linux controller with multiple explicit targets.
- Authenticated BLE PIN pairing, persistent bonds and HID-mode bonded reconnect.
- Clear per-board DISARMED/ARMED/TYPING indicators and visible ping feedback.
- Local device aliases, saved device lists and alias-aware Identify.
- USB text, special keys, Ctrl+Alt+Delete, immediate Stop and STOP ALL.
- Separate saved start countdown (0–60 seconds) and text interval (0–2000 ms).
- Cancelable scheduled sends with fixed targets and readiness checks.
- Dark/light theme target band and state badges.
- App-only firmware updates at 0x10000 that retain NVS bonds.
- Versioned window/startup diagnostics, Windows/Linux setup and launch scripts,
  pinned direct dependencies, component hashes and a package manifest.

## Verification and platform behavior

The desktop suite has 55 tests, including protocol/session checks and offscreen
Qt countdown/cancel/target-snapshot tests. Packaging verification checks the
archive, Python syntax, all hashes and equality to the tested rc13 firmware.
The suite is also run from an extracted distribution before handoff.

User feedback confirmed Linux PIN pairing, HID reconnect and the latest timing
features. The tester reported Windows operation working well with the rc12 bundle;
the newer delay features use shared application logic, but were not separately
reported as Windows hardware-tested. This is recorded coverage, not a claim of
testing every Bluetooth adapter or OS version.

Windows first pairing/PIN entry uses Windows Bluetooth Settings. Linux has an
in-app PIN agent and targeted live discovery during connection. Windows in-app
PIN entry and standalone EXE packaging are not included in this release.

Aliases are local to each controller, not persistent BLE advertising names.
Display labels use an ASCII approximation with a 32-byte limit. Input text is
US-layout ASCII, up to 2048 bytes. USB scheduling can lengthen the requested
character interval; zero means fastest, not zero physical time. Changing the
interval on an older board fails with an explicit firmware-update message
instead of sending at an unintended speed.

The source package excludes virtual environments, local settings, logs,
pairings, deployment credentials and unrelated files. External hosting and
the public Web Bluetooth site are unchanged by this local release.
