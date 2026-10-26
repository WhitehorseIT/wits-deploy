# WITS Deploy desktop app

Native Windows and Linux controller for one or more WITS Deploy boards. It talks directly to each
board through the operating system's Bluetooth stack and loads no code from the web.

## Run it

- **Packaged Linux build:** see the [repository README](../README.md#install-the-desktop-app). Updates
  install from inside the app.
- **From source (Linux):** `bash SETUP-LINUX.sh`, then `bash START-LINUX.sh`. `bash
  INSTALL-LAUNCHER-LINUX.sh` adds an app-menu shortcut; add `--autostart` only if you want it to
  start at sign-in.
- **From source (Windows):** install 64-bit Python 3.11 or newer with the py launcher, then run
  `SETUP-WINDOWS.cmd` once and `START-WINDOWS.cmd` to start. Keep the console window open.
- **Development:** `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python run.py`

Requires Python 3.11 or newer for source runs. See [packaging](../docs/DESKTOP-PACKAGING.md) for
shortcuts, builds and in-app updates.

## The board list

The list at the top shows each saved board: **Target**, **Auto-connect**, **Device** (its friendly
name), **Board state**, **Firmware** and **Last result**. Drag column edges to resize them.

- **Board state:** DISARMED (green), ARMED (red) or TYPING (orange), plus Authenticating, Watching
  and Offline. A disconnected board is never shown as confirmed disarmed.
- **Firmware:** the version the board reports, highlighted green when it is the newest known, yellow
  when an update is available and red for a critical update. Hover for details. The newest known
  version comes from the bundled firmware and, when reachable, the project's latest release. See
  [the update check](../docs/OTA-UPDATES.md#firmware-version-colors-and-the-update-check).
- **Target:** which boards receive text and keys. Every box starts unchecked at launch.
- **Auto-connect:** reconnect this board automatically; see below.

The app restores saved names and addresses at launch. It stores only names and addresses, not PINs
or Bluetooth keys.

## Pairing

Linux's Bluetooth service keeps the actual bond. Use **Connect** for a normal reconnect and reserve
**Re-pair** for a stale bond. A board in HID mode advertises to bonded computers after startup and
after disconnects, so a saved board connects without a button press or a new PIN. Adding a new
computer, or replacing a cleared bond, needs the board's physical pairing window.

- **First or new pairing:** open the board's pairing window (hold PAIR on the board), highlight it,
  and choose **Connect**. On Linux the app registers its own pairing agent and opens a PIN dialog;
  enter the six-digit PIN shown on the board. This does not change the system's default Bluetooth
  agent.
- **Windows:** the app pairs the board itself, the same way as on Linux: open the board's pairing
  window, choose **Connect** and type the PIN into the app's prompt. (The Python Bluetooth library cannot
  do PIN pairing on Windows, so the app asks Windows for it directly.) This is new and still being
  tested; if it fails, pair through **Settings > Bluetooth & devices** first and then choose **Connect**.
  If a bond goes stale, remove it in Windows Settings and pair again.
- **Stale bond:** if a board was factory-flashed or had its bonds cleared, the computer may still
  hold the old one. Hold the board's pairing button until its PIN shows, highlight it, and choose
  **Re-pair**. This removes only that board's local bond.
- The PIN is neither saved nor logged. Canceling PIN entry or choosing Disconnect cancels the
  pairing in progress. **Cancel connection** stops a running attempt, which times out after 25
  seconds on Linux.

A board's first ping must confirm authenticated state before it can send anything. GATT requests
time out after ten seconds, and a disconnect ends a pending request immediately.

## Automatic reconnect

Tick **Auto-connect** for each saved board you want this computer to manage. It is saved separately
from Target. The app watches for the board's HID advertisements, uses the existing bond and requires
an authenticated response; it never starts PIN pairing in the background.

Dropped links retry with 5, 10, 20, 40 and 60 second backoff. A manual **Disconnect** pauses that
board until you click Connect, toggle Auto-connect or restart the app. Turning Auto-connect off
cancels a pending attempt but keeps an established connection. Authentication failures pause retries.
Connection setup, scans and updates share a Bluetooth lock, so attempts take turns.

## Safety behavior

- Every destination must be explicitly checked in the Target column, connected, authenticated,
  physically armed and idle before the app submits text.
- Multi-target text asks for confirmation and reports each board separately.
- Failed or interrupted text is never retried automatically.
- Special keys and Ctrl+Alt+Delete require exactly one target.
- **STOP ALL** is always available. Payload content is never written to the event log or settings.

## Send timing

Two independent controls are saved between runs:

- **Before sending:** 0-60 seconds (default 0), for text and special keys. A visible countdown gives
  you time to focus the target window.
- **Between characters:** 0-2000 ms (default 25), for typing text. Zero selects the fastest loop;
  USB scheduling can lengthen the actual interval. Single key combinations stay atomic.

One delayed operation can be pending at a time. It keeps its original targets, text and timing.
Cancel delayed send, STOP, a target disconnecting or disarming, or closing the app cancels the
countdown, and nothing is sent before it expires.

## Storage controls

For boards with a MicroSD slot, highlight one connected board; the storage controls act on it
regardless of the Target boxes. The status line shows the board's firmware, card capacity, access
mode and throughput since the last refresh.

- **Mount read/write** works from a mounted or unmounted read-only drive without ejecting. The board
  briefly withdraws the drive (about 3.5 seconds) and presents it again writable.
- A read/write grant stays in place if the app closes or Bluetooth drops, because a computer may
  still hold unwritten data. It ends at a confirmed eject, a media error or a board reset.
- **Mount read-only** from read/write needs a safe eject on the computer first.
- Safely eject writable drives before updating firmware or resetting. See
  [USB storage](../docs/STORAGE.md).

## Firmware and app updates

- **OTA Update…** (Bluetooth): highlight one connected, authenticated, disarmed board. The app uses
  the board's model to select the image. Choose **Download latest firmware** (signed, verified), use
  the bundled firmware, or pick a release `.ota.json`. Bluetooth shares airtime between boards, so
  the app offers to disconnect the others and switches Auto-connect off for the duration.
- **USB Flash/Update…**: works without a Bluetooth connection. Choose the physical model, serial port
  and release JSON, then put the board in FLASH mode. *Update working board* keeps pairings;
  *Install blank board / factory recovery* clears settings and suits a first install.
- **Update app…:** appears in the packaged Linux build when a newer signed release exists. It
  downloads, verifies and installs beside the running copy and restarts into it, with an automatic
  fallback if the new version fails to start.

Details and recovery steps: [firmware updates](../docs/OTA-UPDATES.md),
[release signing](../docs/RELEASE-SIGNING.md).

## Closing the app

Closing disconnects each board so it releases its Bluetooth link cleanly and accepts the next
connection at once. With boards connected this can take up to three seconds; a notice with a
countdown explains the wait, and the window stays responsive. With nothing connected the app closes
immediately.

## Diagnostic log

Below the board list, **Copy log** puts the on-screen events on the clipboard, **Save logs…** writes a single
ZIP (the events, the full debug logs, any crash traces and the app and system versions) to a place you
choose, and **Clear log** empties the list. Send the ZIP when you ask for help; GATT payloads, and so typed
text and PINs, are never in the logs.

Every launch writes debug-level application and Bluetooth diagnostics. The file rotates at 4 MiB and
keeps three old copies; GATT write payloads are redacted, so typed text and passwords are not
recorded. The exact path is shown near the top of the app.

| Run type | Log folder |
| --- | --- |
| Source | `desktop/logs/` |
| Packaged Linux | `~/.local/state/wits-deploy/logs/` |
| Packaged Windows | `%LOCALAPPDATA%\Whitehorse IT Solutions\WITS Deploy\logs\` |

Downloaded firmware and update state are kept per user, in `~/.local/share/wits-deploy/` on Linux
and `%LOCALAPPDATA%\Whitehorse IT Solutions\WITS Deploy\data\` on Windows. Linux connections also
record a small read-only BlueZ snapshot (pairing and link state, and the disconnect reason) in the
event log.

**Identify** shows the row's friendly name on the board's screen (ASCII, up to 32 characters). It
works only while the board is authenticated and disarmed, and does not change the Bluetooth name or
the bond.

## Tests

```bash
cd desktop
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests
```

The tests use simulated Bluetooth and USB devices and need neither hardware nor a display.
