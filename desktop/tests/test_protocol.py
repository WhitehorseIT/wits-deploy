import unittest

from wits_keyboard.protocol import (
    MAX_TEXT_BYTES,
    MODIFIER_ALT,
    MODIFIER_CTRL,
    OPCODE_KEY_ACTION,
    OPCODE_TYPE_TEXT,
    PROTOCOL_VERSION,
    ProtocolError,
    SequenceCounter,
    encode_text,
    identify_frame,
    key_frame,
    key_interval_frame,
    parse_status,
    text_frames,
)


class ProtocolTests(unittest.TestCase):
    def test_character_interval_encoding_and_limits(self):
        self.assertEqual(key_interval_frame(0x1234, 500), bytearray((2, 0x14, 0x34, 0x12, 0xF4, 1)))
        self.assertEqual(key_interval_frame(1, 0)[4:], b"\x00\x00")
        with self.assertRaises(ProtocolError):
            key_interval_frame(1, 2001)

    def test_identify_label_is_bounded_printable_ascii_with_legacy_empty_frame(self):
        self.assertEqual(identify_frame(1), bytearray((2, 0x13, 1, 0)))
        self.assertEqual(identify_frame(2, "Café\nDevice"),
                         bytearray((2, 0x13, 2, 0)) + b"Cafe Device")
        frame = identify_frame(3, "A" * 100)
        self.assertEqual(len(frame), 36)
        self.assertTrue(frame.endswith(b"..."))

    def test_sequence_wraps_without_zero(self):
        counter = SequenceCounter()
        counter._next = 0xFFFF
        self.assertEqual(counter.take(), 0xFFFF)
        self.assertEqual(counter.take(), 1)

    def test_key_frame_is_little_endian(self):
        frame = key_frame(0x1234, 2, MODIFIER_CTRL | MODIFIER_ALT)
        self.assertEqual(
            frame,
            bytearray((PROTOCOL_VERSION, OPCODE_KEY_ACTION, 0x34, 0x12, 2, 5)),
        )

    def test_text_is_chunked_and_flagged(self):
        frames = text_frames("A" * 121, SequenceCounter())
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0][:5], bytearray((2, OPCODE_TYPE_TEXT, 1, 0, 1)))
        self.assertEqual(frames[1][:5], bytearray((2, OPCODE_TYPE_TEXT, 2, 0, 2)))
        self.assertEqual(len(frames[0]), 125)
        self.assertEqual(len(frames[1]), 6)

    def test_rejects_unicode_and_oversize(self):
        with self.assertRaises(ProtocolError):
            encode_text("snowman: ☃")
        with self.assertRaises(ProtocolError):
            encode_text("A" * (MAX_TEXT_BYTES + 1))

    def test_status_decoding(self):
        status = parse_status(bytes((2, 0, 0xEF, 0xBE, 0x07)))
        self.assertEqual(status.sequence, 0xBEEF)
        self.assertTrue(status.authenticated)
        self.assertTrue(status.armed)
        self.assertTrue(status.typing)

    def test_status_requires_exact_size_and_version(self):
        with self.assertRaises(ProtocolError):
            parse_status(bytes((2, 0)))
        with self.assertRaises(ProtocolError):
            parse_status(bytes((1, 0, 1, 0, 0)))


if __name__ == "__main__":
    unittest.main()
