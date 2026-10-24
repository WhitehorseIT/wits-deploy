# WITS Keyboard Controller

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
`bash START-LINUX.sh`. A standalone Windows executable has not been built.

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

## Bluetooth firmware updates (dev8)

Highlight one connected, authenticated, disarmed board and choose Update
firmware. Select its model-specific .ota.json beside the matching .app.bin.
Both T-QT Pro and Waveshare7 need one initial USB bootstrap to OTA-capable
firmware. The existing paired BLE connection carries the upload; your Wi-Fi/
internet connection stays unchanged. Safely eject writable USB storage first.
Keep power on and follow progress in the app; the Waveshare display pauses
during flash writes. Verified uploads restart in PROGRAM. Hardware OTA testing
is pending. See the project's OTA-UPDATES.md for bootstrap and recovery.

## App dev9 firmware workflow

One `WITS-Keyboard-Release-VERSION.ota.json` serves both supported models.
Extract the firmware ZIP with its folders intact. For Bluetooth, connect and
disarm a board, highlight it, then Update firmware; the app reads its model and
selects the matching image. Old single-model manifests remain supported.

Flash over USB also supports blank boards. Select the physical model, port
and same JSON, enter FLASH, then choose a working-board update (inactive slot,
verify, commit; preserves pairings) or factory installation (clears settings).
Use UART on Waveshare. Keep power connected and press RESET after verification.
Setup now installs esptool/pyserial too; rerun setup if using a previous venv.

Bluetooth uploads display KiB/s and estimated remaining time. Linux explicitly
queries MTU before upload and releases the temporary write lock; packet limits
are refreshed during transfer. New hardware speed/USB checks remain pending.
