"""Wire protocol shared by the native controller and ESP32 firmware."""

from __future__ import annotations

from dataclasses import dataclass
import unicodedata
import json

SERVICE_UUID = "62fa47a0-d77c-4045-9e7e-81d5a93931cc"
RX_UUID = "2bcd9577-d0b1-4164-9ff4-88f0cc29cbc3"
TX_UUID = "7cb2a248-dad7-4149-a36f-fc2dfe91675d"
INFO_UUID = "3abfae15-ec3c-49db-a65d-17c8d977c102"

PROTOCOL_VERSION = 2

OPCODE_PING = 0x01
OPCODE_TYPE_TEXT = 0x10
OPCODE_STOP = 0x11
OPCODE_KEY_ACTION = 0x12
OPCODE_IDENTIFY = 0x13
OPCODE_KEY_INTERVAL = 0x14
OPCODE_STORAGE_MODE = 0x15

TEXT_FLAG_START = 0x01
TEXT_FLAG_END = 0x02

STATUS_OK = 0x00
STATUS_TYPING_COMPLETE = 0x10
STATUS_TYPING_CANCELED = 0x11
STATUS_STATE_CHANGED = 0x12
STATUS_KEY_COMPLETE = 0x13
STATUS_KEY_CANCELED = 0x14

MAX_TEXT_BYTES = 2048
TEXT_CHUNK_BYTES = 120
MAX_IDENTIFY_LABEL_BYTES = 32
DEFAULT_KEY_INTERVAL_MS = 25
MAX_KEY_INTERVAL_MS = 2000

KEY_BACKSPACE = 0x01
KEY_DELETE = 0x02
KEY_ENTER = 0x03
KEY_TAB = 0x04
KEY_ESCAPE = 0x05
KEY_LEFT = 0x06
KEY_RIGHT = 0x07
KEY_UP = 0x08
KEY_DOWN = 0x09
KEY_HOME = 0x0A
KEY_END = 0x0B
KEY_PAGE_UP = 0x0C
KEY_PAGE_DOWN = 0x0D
KEY_INSERT = 0x0E
KEY_F1 = 0x10
KEY_F12 = 0x1B
KEY_SPACE = 0x20

MODIFIER_CTRL = 0x01
MODIFIER_SHIFT = 0x02
MODIFIER_ALT = 0x04
MODIFIER_GUI = 0x08

STATUS_MESSAGES = {
    1: "protocol version mismatch",
    2: "unknown command",
    3: "malformed command",
    4: "board is not armed",
    5: "board is busy",
    6: "text contains an unsupported character",
    7: "text exceeds the board limit",
    8: "text transfer is out of sequence",
    9: "USB keyboard rejected a character",
    10: "unsupported key",
    11: "this board does not support storage",
    12: "MicroSD card is unavailable; insert the card and reset the board",
    13: "safely eject the USB drive on the target computer before changing its access mode",
}


class ProtocolError(ValueError):
    """Raised when a frame or payload violates the protocol."""


@dataclass(frozen=True, slots=True)
class BoardInfo:
    firmware: str
    board: str
    supported: bool
    present: bool
    exported: bool
    writable: bool
    ejected: bool
    error: bool
    bytes: int
    io: dict | None = None  # cumulative storage counters; newer firmware only


IO_FIELDS = ("rb", "wb", "rc", "wc", "mx", "rt", "wt", "ru", "wu", "sl", "er")


def parse_board_info(data: bytes | bytearray) -> BoardInfo:
    if not 1 <= len(data) <= 512:
        raise ProtocolError("invalid board information length")
    try:
        value = json.loads(data)
    except (UnicodeError, ValueError) as error:
        raise ProtocolError("invalid board information JSON") from error
    if not isinstance(value, dict) or type(value.get("schema")) is not int or value["schema"] != 1:
        raise ProtocolError("unsupported board information schema")
    for field in ("firmware", "board"):
        if not isinstance(value.get(field), str) or not 1 <= len(value[field]) <= 32 \
                or any(not 0x20 <= ord(c) <= 0x7e for c in value[field]):
            raise ProtocolError(f"invalid board {field}")
    fields = ("supported", "present", "exported", "writable", "ejected", "error")
    if any(type(value.get(field)) is not bool for field in fields):
        raise ProtocolError("invalid storage state flags")
    if type(value.get("bytes")) is not int or not 0 <= value["bytes"] <= (1 << 63) - 1:
        raise ProtocolError("invalid storage capacity")
    if value["writable"] and (not value["exported"] or not value["present"] or value["error"]):
        raise ProtocolError("inconsistent writable storage state")
    io = value.get("io")
    if io is not None:
        if not isinstance(io, dict) or set(io) != set(IO_FIELDS) or \
                any(type(io[key]) is not int or not 0 <= io[key] < (1 << 64) for key in IO_FIELDS):
            raise ProtocolError("invalid storage I/O counters")
    return BoardInfo(**{field: value[field] for field in BoardInfo.__dataclass_fields__ if field != "io"}, io=io)


@dataclass(frozen=True, slots=True)
class StatusFrame:
    status: int
    sequence: int
    authenticated: bool
    armed: bool
    typing: bool

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK

    @property
    def message(self) -> str:
        return STATUS_MESSAGES.get(self.status, f"board status {self.status}")


class SequenceCounter:
    def __init__(self) -> None:
        self._next = 1

    def take(self) -> int:
        value = self._next
        self._next = 1 if value == 0xFFFF else value + 1
        return value


def _header(opcode: int, sequence: int) -> bytearray:
    if not 1 <= sequence <= 0xFFFF:
        raise ProtocolError("sequence must be between 1 and 65535")
    return bytearray(
        (PROTOCOL_VERSION, opcode, sequence & 0xFF, (sequence >> 8) & 0xFF)
    )


def command_frame(opcode: int, sequence: int) -> bytearray:
    return _header(opcode, sequence)


def storage_mode_frame(sequence: int, allow_writes: bool) -> bytearray:
    if type(allow_writes) is not bool:
        raise ProtocolError("storage write permission must be a boolean")
    return command_frame(OPCODE_STORAGE_MODE, sequence) + bytes([int(allow_writes)])


def identify_frame(sequence: int, label: str = "") -> bytearray:
    """Optional printable label; the board's built-in font is ASCII only."""
    normalized = unicodedata.normalize("NFKD", " ".join(label.split()))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    display = normalized.encode("ascii", "replace")
    display = bytes(value if 0x20 <= value <= 0x7E else ord("?") for value in display)
    if len(display) > MAX_IDENTIFY_LABEL_BYTES:
        display = display[:MAX_IDENTIFY_LABEL_BYTES - 3] + b"..."
    return command_frame(OPCODE_IDENTIFY, sequence) + display


def key_frame(sequence: int, key_code: int, modifiers: int = 0) -> bytearray:
    if not 0 <= key_code <= 0xFF or not 0 <= modifiers <= 0xFF:
        raise ProtocolError("key code and modifiers must fit in one byte")
    frame = _header(OPCODE_KEY_ACTION, sequence)
    frame.extend((key_code, modifiers))
    return frame


def key_interval_frame(sequence: int, milliseconds: int) -> bytearray:
    if type(milliseconds) is not int or not 0 <= milliseconds <= MAX_KEY_INTERVAL_MS:
        raise ProtocolError(f"character delay must be 0–{MAX_KEY_INTERVAL_MS} ms")
    return command_frame(OPCODE_KEY_INTERVAL, sequence) + milliseconds.to_bytes(2, "little")


def encode_text(text: str) -> bytearray:
    if not text:
        raise ProtocolError("enter or paste text first")
    if any(
        character not in "\t\n" and not 0x20 <= ord(character) <= 0x7E
        for character in text
    ):
        raise ProtocolError("only printable US-ASCII, Tab, and newline are supported")
    encoded = bytearray(text, "ascii")
    if len(encoded) > MAX_TEXT_BYTES:
        wipe(encoded)
        raise ProtocolError(f"text exceeds the {MAX_TEXT_BYTES}-byte limit")
    return encoded


def text_frames(text: str, sequences: SequenceCounter) -> list[bytearray]:
    encoded = encode_text(text)
    frames: list[bytearray] = []
    try:
        for offset in range(0, len(encoded), TEXT_CHUNK_BYTES):
            chunk = encoded[offset : offset + TEXT_CHUNK_BYTES]
            first = offset == 0
            last = offset + len(chunk) == len(encoded)
            flags = (TEXT_FLAG_START if first else 0) | (TEXT_FLAG_END if last else 0)
            frame = _header(OPCODE_TYPE_TEXT, sequences.take())
            frame.append(flags)
            frame.extend(chunk)
            frames.append(frame)
    finally:
        wipe(encoded)
    return frames


def parse_status(data: bytes | bytearray | memoryview) -> StatusFrame:
    raw = bytes(data)
    if len(raw) != 5:
        raise ProtocolError(f"status response must be 5 bytes, received {len(raw)}")
    if raw[0] != PROTOCOL_VERSION:
        raise ProtocolError(
            f"protocol mismatch: board={raw[0]}, app={PROTOCOL_VERSION}"
        )
    flags = raw[4]
    return StatusFrame(
        status=raw[1],
        sequence=raw[2] | (raw[3] << 8),
        authenticated=bool(flags & 0x01),
        armed=bool(flags & 0x02),
        typing=bool(flags & 0x04),
    )


def wipe(buffer: bytearray) -> None:
    for index in range(len(buffer)):
        buffer[index] = 0
