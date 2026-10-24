#!/usr/bin/env python3
"""Capture Waveshare UART boot/panic output; opening the adapter may reset it."""
import argparse
from datetime import datetime
from pathlib import Path
import sys
import time

import serial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", nargs="?", default="/dev/ttyACM0")
    parser.add_argument("--seconds", type=float, default=180, help="capture duration (default 180 seconds)")
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("capture duration must be positive")
    directory = Path(__file__).resolve().parents[1] / "desktop/logs"
    directory.mkdir(exist_ok=True)
    path = directory / f"waveshare-uart-{datetime.now():%Y%m%d-%H%M%S-%f}.log"
    connection = serial.Serial(port=None, baudrate=115200, timeout=0.2, exclusive=True)
    # Avoid an intentional reset. The OS/adapter can still pulse these lines
    # at open before the requested levels take effect; leave the port open.
    connection.dtr = False
    connection.rts = False
    connection.port = args.port
    try:
        connection.open()
    except serial.SerialException as error:
        print(f"Cannot open {args.port}: {error}", file=sys.stderr)
        return 1
    print(f"Listening on {args.port} at 115200 baud. Log: {path}", flush=True)
    print("Opening UART may reset the board. Leave this console open, then hold touchscreen HID.", flush=True)
    print("Press RESET first only if needed. Ctrl+C stops capture.", flush=True)
    pending = bytearray()
    def emit(raw, output):
        line = raw.decode("utf-8", errors="replace").rstrip("\r")
        stamped = f"[{datetime.now():%H:%M:%S.%f}] {line}\n"
        output.write(stamped)
        output.flush()
        print(line, flush=True)
    with connection, path.open("x", encoding="utf-8") as output:
        output.write(f"UART capture port={args.port} baud=115200 started={datetime.now().isoformat()}\n")
        output.flush()
        deadline = time.monotonic() + args.seconds
        try:
            while time.monotonic() < deadline:
                pending.extend(connection.read(min(max(connection.in_waiting, 1), 4096)))
                while b"\n" in pending:
                    line, _, rest = pending.partition(b"\n")
                    pending[:] = rest
                    emit(line, output)
                if len(pending) >= 8192:
                    emit(bytes(pending), output)
                    pending.clear()
        except KeyboardInterrupt:
            pass
        except serial.SerialException as error:
            emit(f"Serial disconnected: {error}".encode(), output)
        finally:
            if pending:
                emit(bytes(pending), output)
    print(f"Capture saved: {path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
