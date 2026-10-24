"""USB flashing backend: validated factory install or inactive-slot update."""
import argparse
import binascii
import importlib.util
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
from .firmware_update import load_release
from .runtime import frozen, worker_command

LAYOUTS = {"tqtpro": (4, (0x10000, 0x200000), 0x1f0000),
           "waveshare7": (8, (0x10000, 0x340000), 0x330000),
           "waveshare147": (16, (0x10000, 0x650000), 0x640000)}


def update_plan(otadata: bytes):
    """Select the other slot and metadata sector, retaining the current copy.

    OTA select entries use CRC32(seq, 0xffffffff), per ESP-IDF otatool.py.
    State 2 is VALID; 0xffffffff is legacy UNDEFINED; 0/1 need a normal boot
    and confirmation before another update. Invalid/aborted copies are ignored.
    """
    if len(otadata) != 0x2000:
        raise ValueError("Invalid OTA selection data length")
    entries = []
    for index in (0, 1):
        raw = otadata[index * 0x1000:index * 0x1000 + 32]
        seq, state, crc = struct.unpack_from("<I", raw)[0], struct.unpack_from("<I", raw, 24)[0], struct.unpack_from("<I", raw, 28)[0]
        if 0 < seq < 0xffffffff and crc == (binascii.crc32(raw[:4], 0xffffffff) & 0xffffffff):
            if state in (3, 4): continue
            if state not in (0, 1, 2, 0xffffffff): raise ValueError("Unknown OTA boot state; use factory recovery")
            entries.append((seq, index, state))
    if entries:
        seq, current_copy, state = max(entries)
        if state in (0, 1): raise ValueError("Boot the current firmware normally once before updating again")
        active = (seq - 1) % 2
        other_copy = 1 - current_copy
    else:
        if otadata != b"\xff" * 0x2000:
            raise ValueError("OTA selection data is corrupt; use factory recovery")
        seq, active, other_copy = 1, 0, 0
    if seq >= 0xfffffff0: raise ValueError("OTA sequence exhausted; use factory recovery")
    next_seq = seq + 1
    target = 1 - active
    assert (next_seq - 1) % 2 == target
    entry = struct.pack("<I20sII", next_seq, b"\xff" * 20, 0,
                        binascii.crc32(struct.pack("<I", next_seq), 0xffffffff) & 0xffffffff)
    return target, 0xe000 + other_copy * 0x1000, entry + b"\xff" * (0x1000 - len(entry))


def esptool_prefix():
    if frozen():
        return worker_command("esptool")
    if importlib.util.find_spec("esptool"):
        return [sys.executable, "-m", "esptool"]
    # Developer checkout fallback; packaged Windows/Linux setups install the
    # pinned esptool dependency instead of depending on PlatformIO.
    local = Path.home() / ".platformio/packages/tool-esptool/esptool"
    if sys.platform == "linux" and local.is_file(): return [str(local)]
    raise RuntimeError("esptool is missing. Run the app's setup script again.")


class SerialFlasher:
    def __init__(self, port, prefix=None):
        self.port, self.first = port, True
        self.prefix = prefix if prefix is not None else esptool_prefix()

    def command(self, *args):
        command = self.prefix + ["--chip", "esp32s3", "--port", self.port, "--baud", "460800",
            "--before", "default-reset" if self.first else "no-reset", "--after", "no-reset"] + list(args)
        self.first = False
        output = []
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                              creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0) as process:
            for line in process.stdout:
                print(line, end="", flush=True)
                output.append(line)
            if process.wait(): raise RuntimeError("Serial flashing failed; see the output above")
        return "".join(output)

    def flash(self, manifest, board, factory=False):
        release = load_release(manifest)
        image = release.select(board, factory=factory)
        factory_image = image if factory else release.select(board, factory=True)
        mb, slots, slot_size = LAYOUTS[board]
        if len(image.data) > (mb * 1024 * 1024 if factory else slot_size):
            raise ValueError("Image exceeds this board's flash/slot size")
        probe = self.command("flash-id")  # --chip esp32s3 also rejects other chips.
        match = re.search(r"Detected flash size:\s*(\d+)\s*MB", probe)
        if not match or int(match[1]) != mb:
            raise ValueError(f"Selected model requires {mb}MB flash; refusing a mismatched board")
        with tempfile.TemporaryDirectory(prefix="wits-usb-") as directory:
            root = Path(directory)
            firmware = root / ("firmware.factory.bin" if factory else "firmware.app.bin")
            firmware.write_bytes(image.data)
            if factory:
                print("Installing factory image; existing pairings/settings in the image range will be cleared.", flush=True)
                self.command("write-flash", "0x0", str(firmware))
                self.command("verify-flash", "0x0", str(firmware))
            else:
                table, metadata = root / "partitions.bin", root / "otadata.bin"
                self.command("read-flash", "0x8000", "0x1000", str(table))
                if table.read_bytes() != factory_image.data[0x8000:0x9000]:
                    raise ValueError("Board partition layout differs from this release; use factory installation")
                self.command("read-flash", "0xe000", "0x2000", str(metadata))
                target, metadata_offset, metadata_bytes = update_plan(metadata.read_bytes())
                print(f"Writing inactive app{target} at {slots[target]:#x}; preserving current firmware and pairings.", flush=True)
                self.command("write-flash", hex(slots[target]), str(firmware))
                self.command("verify-flash", hex(slots[target]), str(firmware))
                commit = root / "ota-selection.bin"
                commit.write_bytes(metadata_bytes)
                print("Image verified. Selecting new firmware using the other OTA metadata sector.", flush=True)
                self.command("write-flash", hex(metadata_offset), str(commit))
                self.command("verify-flash", hex(metadata_offset), str(commit))
            print(f"SUCCESS: {board} {image.version} verified. Press RESET, then enter HID.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--board", choices=tuple(LAYOUTS), required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--factory", action="store_true")
    args = parser.parse_args()
    try:
        SerialFlasher(args.port).flash(args.manifest, args.board, args.factory)
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__": sys.exit(main())
