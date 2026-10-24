# rc13 — configurable text pacing

Adds authenticated opcode `0x14`: the four-byte protocol-v2 header followed
by a little-endian uint16 character interval, 0–2000 ms. The board rejects
changes while text or a key action is active. Default is 25 ms and resets
per connection. The USB output loop uses that interval between text characters;
loop/USB scheduling may lengthen the effective delay. Zero is fastest.

The desktop now has separate Before sending (seconds) and Between characters
(milliseconds) controls. The first is an app-side cancelable countdown for
text and special keys; this firmware update is needed for non-default text
pacing. Old clients retain the 25 ms default. The updated app accepts an old
board at the default interval and gives an update-required error if asked to
change timing on unsupported firmware.

Update a working rc9–rc12 T-QT Pro using the app-only image at `0x10000` to
preserve NVS bonds. All rc12 reconnect/physical pairing behavior is retained.

Hardware validation remains pending. Suggested test: start delay 5 seconds,
character interval 500 ms, send ABCD to a focused editor. Expect the first
character after the countdown, then approximately half-second spacing.
Verify cancel/STOP ALL/disarm prevent a pending send, then reset both timing
controls to 0 seconds and 25 ms and verify normal typing.
