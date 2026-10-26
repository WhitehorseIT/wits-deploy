# Security policy

WITS Deploy types text and product keys into other computers and updates device
firmware, so security reports are taken seriously.

## Reporting a vulnerability

Please report suspected vulnerabilities privately by email to
**info@whitehorseit.com**. Do not open a public issue or pull request for a
security problem.

Helpful details:

- The component affected: firmware (and board model), desktop app, USB flasher,
  web console, or release/update files.
- The firmware and app version (shown in the app and on the board's screen).
- Steps to reproduce, and what an attacker would need (physical access, a paired
  computer, Bluetooth range, and so on).

## What is in scope

- Bypassing Bluetooth pairing, the on-screen PIN, or the physical pairing window.
- Using the control, information, or firmware-update channels without an
  authenticated, encrypted connection.
- Making a board type, arm itself, or change storage permissions without the
  intended physical action or authenticated control session.
- Firmware update or flashing flaws, such as accepting an unverified image.
- Release signing flaws: accepting a manifest or download that was not signed by a trusted key, a
  downgrade to an older release, or an unsafe path or link in a downloaded archive (see
  [release signing](docs/RELEASE-SIGNING.md)).
- Leaking typed text, PINs, or keys through logs, files, or the web console.

## Supported versions

This project is in active development. Security fixes go into the latest
release only.
