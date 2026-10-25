# WITS Deploy Controller

Native Windows/Linux controller for one or more WITS Deployment Keyboards.
It talks directly to each board through the operating system's BLE stack; it
does not load executable UI code from the public website.

Stable release: **0.1.0**. Requires Python 3.11 or newer. The source release
includes setup/launch scripts and pinned direct dependencies in
`requirements-release.txt`. Firmware is the tested rc13 binary promoted
unchanged to 0.1.0.

## Development setup

```bash
cd desktop
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run.py
```

On Windows, extract the release and run `SETUP-WINDOWS.cmd`, then
`START-WINDOWS.cmd`. On Linux, run `bash SETUP-LINUX.sh`, then
`bash START-LINUX.sh`. Run `bash INSTALL-LAUNCHER-LINUX.sh` for an app-menu
shortcut; append `--autostart` only if sign-in launching is wanted.

App dev11 includes native Windows/Linux packaging support and a GitHub Actions
build workflow. The Linux native package passed local startup checks; Windows
builds remain pending. See [the build and launcher guide](../docs/DESKTOP-PACKAGING.md).
Source setup remains available while those candidates are tested.

## Pairing

The app restores its known device list and friendly aliases at launch. Target
checkboxes start unchecked. Linux's Bluetooth service retains the actual bond;
the app stores only names and addresses, not PINs or Bluetooth keys. Use
**Connect** for a normal reconnect, and reserve **Re-pair** for a stale bond.
On Linux, saved devices are resolved from BlueZ's cache before trying discovery.
With rc12 or newer, a board in HID mode advertises for bonded computers at
startup and after disconnects. Select a saved board and Connect without
holding a button or entering another PIN. Older firmware requires opening
the advertising/pairing window with left first. Adding a new computer or
replacing a cleared bond still requires the physical pairing window.

For a first/new pairing, put the board into its physical pairing window before selecting Connect. The
application asks Bleak to pair before accessing the authenticated GATT service.
On Linux, the application registers its own BlueZ pairing agent and opens a
PIN dialog in the controller. Enter the six-digit PIN shown on the board.
This does not change the system's default Bluetooth agent. On Windows, pair
through Bluetooth Settings first and then Connect in the app. The installed
Bleak Windows backend only implements confirmation-style pairing, so an
app-initiated fresh pairing may not handle the board's PIN requirement.

An existing saved bond normally reconnects without a PIN prompt. To test a
fresh PIN exchange, use Re-pair after opening the board's pairing window.
Canceling PIN entry or Disconnect cancels the pending pairing operation.
The PIN is neither saved nor logged. On Windows, prefer removing a stale
bond and re-pairing through Windows Settings for now; the app's Re-pair button
automatically retries an unverified fresh-pairing path on that platform.

Connect immediately displays a running connection attempt and elapsed time.
While it runs, use **Cancel connection** to stop it, or **Re-pair** to replace
the saved bond. On Linux the link connection times out after 25 seconds once
PIN pairing is finished or an existing bond is found. A saved bond does not
trigger another PIN prompt by itself.

If a board was factory-flashed or had its bonds cleared, the computer may still
hold a stale bond. Hold the board's left button until the PIN is visible,
highlight it in the device list, and choose **Re-pair**. This removes only that
board's local OS bond, rediscovers it, and requests a new PIN.

The board's first ping must confirm authenticated state before it is eligible
for sending. A notification subscription by itself is not treated as proof
of authentication. GATT requests time out after ten seconds, including time
spent waiting for the write; a disconnect ends a pending request immediately.

## Safety behavior

- Each device row has a live Board state badge: DISARMED (green), ARMED
  (red), or TYPING (orange). Authenticating and Offline are distinct states;
  a disconnected board is not presented as confirmed disarmed. Badge colors
  and text remain visible when a row is highlighted in either theme.
- Every destination must be explicitly checked in the Target column.
- Every destination must be connected, authenticated, physically armed, and
  idle before the application will submit text.
- Multi-target text requires confirmation and reports each board separately.
- Failed or interrupted text is never retried automatically.
- Special keys and Ctrl+Alt+Delete require exactly one target.
- STOP ALL is always available.
- Payload content is never written to the event log or settings.

## Send timing

Two independent controls are saved between app runs:

- **Before sending:** 0–60 seconds, default 0. Applies to text and special
  keys/combos. A visible countdown gives time to focus the target window.
- **Between characters:** 0–2000 ms, default 25. Applies to text typing on
  the board. Zero selects the fastest device loop; USB and loop scheduling
  can lengthen the actual interval. Single special-key combos remain atomic.

One delayed operation can be pending at a time. It retains the original
targets, text and timing settings; changing target checkboxes does not retarget
it. Cancel delayed send, Stop selected (for a pending target), STOP ALL, closing
the app, or a target disconnect/disarm/busy state cancels the countdown. No
text is sent before expiry. Canceling preserves unsent editor content; edits
made during the countdown are not cleared when the original text dispatches.
The board must be connected, authenticated, armed and idle when scheduling
and when the countdown finishes.

Changing character pacing requires **0.1.0 (or rc13)**. The app acknowledges
the timing setting before sending text, and reports a firmware-update error
without sending text if an older board rejects it. The original 25 ms setting
continues to work on older firmware. The start countdown is app-only and
works with existing firmware. Per-connection firmware pacing resets to 25 ms
on reconnect and is reapplied by the app as needed.

## Diagnostic log

Ping feedback appears beneath the device buttons, in the footer, in Last
result, and in the event log: sent/awaiting reply, acknowledged with round-trip
milliseconds, or failed. The dedicated ping result remains visible even when
the device table's Last result column is clipped.

Every launch writes DEBUG-level application and Bleak diagnostics to
`logs/wits-keyboard-debug.log`. The file rotates at 4 MiB and keeps three old
copies. GATT write payloads are redacted, so deployment text and passwords are
not recorded. The exact path is also shown near the top of the application.

The Identify action requires firmware with opcode `0x13`; it is accepted only
while the board is authenticated and physically disarmed.
With firmware rc10 or later, Identify sends the current friendly name from the
device row and displays it above the fixed hardware ID. Older firmware falls
back to showing the ID and reports that a firmware update is needed for names.
The label is temporary; it does not change the BLE advertised name or bond.
The small board font uses an ASCII approximation, limited to 32 characters.

Linux connections also record a small BlueZ snapshot of the selected board's
pairing/link state and the adapter's power/discovery state. When BlueZ emits
its `Disconnected` reason signal, the event log distinguishes authentication
failure, timeout, and a local/remote disconnect. This observer is read-only;
it does not change adapter settings, bonds or the system's default agent.
Older BlueZ versions may not supply the reason signal, in which case normal
connection errors still appear. Only selected metadata fields are recorded.

## Tests

The protocol tests do not require Bluetooth or Qt:

```bash
cd desktop
python3 -m unittest discover -s tests -v
```

## Bluetooth firmware updates

Highlight one connected, authenticated, disarmed board and choose **OTA
Update…**. Select the common release `.ota.json`, keeping its image folders
alongside it. The app reads the board model and selects its matching image;
legacy single-model manifests remain supported. OTA-capable firmware must be
installed over USB first (dev8+ on original boards, dev10+ on Waveshare147).
Your normal network connection stays connected.

Safely eject writable USB storage first and keep power on. Progress includes
KiB/s and estimated time. The 7-inch RGB screen pauses during writes; SPI
screens retain their update message. Verified uploads reboot to PROGRAM.
See [update and recovery](../docs/OTA-UPDATES.md) for details and test limits.

## USB flashing and the 1.47-inch board (app dev10)

**USB Flash/Update…** supports blank boards without a Bluetooth connection.
Select the physical model, serial port and same common release JSON. Enter
FLASH/bootloader mode, close serial monitors and safely eject writable storage.
Working-board updates verify the layout and inactive app before committing;
factory installation clears settings and is appropriate for a first install.
Press RESET after verification. Setup installs esptool/pyserial; rerun setup
if using an older environment.

Waveshare7 uses its UART connector for flashing and separate USB for keyboard/
storage. Waveshare147 uses its single USB-C connector. Select **Waveshare
1.47-inch touch** for the new board; do not substitute another model. This port
is a first bring-up build with hardware tests pending. See its
[first-flash guide](../docs/boards/WAVESHARE147.md).

Bluetooth uses authenticated model information; blank-board USB installation
requires you to choose the exact physical model. Flash capacity checks catch
many mismatches but cannot identify all unrelated boards with matching memory.

## Automatic reconnect (app dev13)

Check the separate **Auto-connect** box for each saved board you want this PC
to manage. This choice is saved independently of Target; Target still starts
unchecked. The app watches HID advertisements, uses an existing OS bond and
requires an authenticated response. It never starts PIN pairing in the
background. First pairing and stale bonds use Connect/Re-pair manually.

Dropped links retry with 5/10/20/40/60-second backoff. Manual Disconnect pauses
that board until Connect, toggling Auto-connect, or restarting the app. Turning
Auto-connect off cancels its pending attempt but keeps an established connection.
Connection setup, background/explicit scans and OTA transfers share an adapter
lock; attempts are serialized. Watching/connecting/retry/pause messages appear
in Last result and the event log. Authentication failures pause retries.

## Writable USB storage lifetime (firmware dev13)

A granted R/W USB export stays writable when this app closes, Bluetooth drops,
or another control connection is established. This also applies when opening
pairing or clearing bonds. The USB host may still have cached writes, so BLE
control changes must not write-protect a mounted filesystem. Keyboard output
still stops and disarms on disconnect.

Read-only is the boot default. Granting R/W or changing mode requires the usual
authenticated, disarmed operation and host safe eject. A grant lasts until
confirmed host eject, media error or reset. OTA/programming restart remains
blocked while a writable host export needs eject. There is no automatic host
filesystem flush and no grace timer that assumes cached writes are complete.
Dev12 and earlier revoked writes immediately on disconnect/reconnect, which
can interrupt a copy. Flash dev13 for this fix; recompiling only the app is
not sufficient. Verify any previously interrupted copies against their source.
