import binascii
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from wits_keyboard.usb_flash import SerialFlasher, update_plan


def selection(seq, state=2):
    return struct.pack("<I20sII", seq, b"\xff" * 20, state,
                       binascii.crc32(struct.pack("<I", seq), 0xffffffff) & 0xffffffff)


class SelectionTests(unittest.TestCase):
    def test_known_esp_idf_boot_app0_entry_crc_and_slot(self):
        # Published SDK boot_app0.bin starts with this sequence/CRC vector.
        entry = bytes.fromhex("01000000" + "ff" * 24 + "9a984347")
        target, offset, _ = update_plan(entry + b"\xff" * (0x2000 - 32))
        self.assertEqual((target, offset), (1, 0xf000))

    def test_initial_layout_writes_app1_and_retains_factory_selection_fallback(self):
        target, offset, data = update_plan(b"\xff" * 0x2000)
        self.assertEqual((target, offset), (1, 0xe000))
        self.assertEqual(data[:32], selection(2, 0))

    def test_alternates_slots_and_writes_only_other_metadata_sector(self):
        for seq, copy in ((1, 0), (2, 1), (3, 0), (4, 1)):
            original = bytearray(b"\xff" * 0x2000)
            original[copy * 0x1000:copy * 0x1000 + 32] = selection(seq)
            target, offset, data = update_plan(bytes(original))
            self.assertEqual(target, 1 - (seq - 1) % 2)
            self.assertEqual(offset, 0xe000 + (1 - copy) * 0x1000)
            committed = bytearray(original)
            start = offset - 0xe000
            committed[start:start + 0x1000] = data
            self.assertEqual(committed[copy * 0x1000:copy * 0x1000 + 32], selection(seq))
            self.assertEqual(data[:32], selection(seq + 1, 0))

    def test_corruption_and_unconfirmed_boot_refuse_an_update(self):
        for data in (b"bad", b"\0" * 0x2000):
            with self.assertRaises(ValueError): update_plan(data)
        for state in (0, 1):
            data = selection(2, state) + b"\xff" * (0x2000 - 32)
            with self.assertRaisesRegex(ValueError, "Boot"):
                update_plan(data)


class UsbFlashTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = bytearray(400)
        self.app[0] = 0xe9
        self.app[32:36] = bytes.fromhex("3254cdab")
        self.factory = bytearray(b"\xff" * 0x10000) + self.app
        self.factory[0] = 0xe9
        self.factory[0x8000:0x9000] = bytes(range(256)) * 16
        (self.root / "test.app.bin").write_bytes(self.app)
        (self.root / "test.factory.bin").write_bytes(self.factory)
        def descriptor(name, data):
            return dict(filename=name, size=len(data), sha256=hashlib.sha256(data).hexdigest())
        self.manifest = self.root / "release.ota.json"
        app = descriptor("test.app.bin", self.app)
        app.update(chip="esp32s3", factory=descriptor("test.factory.bin", self.factory))
        self.manifest.write_text(json.dumps(dict(schema=2, firmware="test", images={"tqtpro": app})))
        owner = self
        class Fake(SerialFlasher):
            def __init__(self):
                self.operations = []
                self.fail_verify = False
                self.flash_mb = 4
                self.bad_layout = False
                self.sequence = 2
            def command(self, *args):
                self.operations.append(args[:2])
                if args[0] == "flash-id": return f"Detected flash size: {self.flash_mb}MB"
                if args[0] == "read-flash":
                    data = (bytes(owner.factory[0x8000:0x9000]) if not self.bad_layout else b"bad") if args[1] == "0x8000" else selection(self.sequence) + b"\xff" * (0x2000 - 32)
                    Path(args[-1]).write_bytes(data)
                if args[0] == "verify-flash" and self.fail_verify:
                    raise RuntimeError("verification failed")
                return ""
        self.flasher = Fake()

    def test_update_after_ota_targets_app0_then_commits_only_after_verification(self):
        self.flasher.flash(self.manifest, "tqtpro")
        writes = [operation for operation in self.flasher.operations if operation[0] == "write-flash"]
        self.assertEqual(writes, [("write-flash", "0x10000"), ("write-flash", "0xf000")])
        self.assertLess(self.flasher.operations.index(("verify-flash", "0x10000")),
                        self.flasher.operations.index(("write-flash", "0xf000")))

    def test_failed_image_verification_never_changes_boot_selection(self):
        self.flasher.fail_verify = True
        with self.assertRaisesRegex(RuntimeError, "verification"):
            self.flasher.flash(self.manifest, "tqtpro")
        self.assertNotIn(("write-flash", "0xf000"), self.flasher.operations)

    def test_wrong_flash_size_or_partition_layout_causes_no_writes(self):
        for flash_mb, bad_layout in ((8, False), (4, True)):
            self.flasher.operations.clear()
            self.flasher.flash_mb, self.flasher.bad_layout = flash_mb, bad_layout
            with self.assertRaises(ValueError): self.flasher.flash(self.manifest, "tqtpro")
            self.assertFalse(any(op[0] == "write-flash" for op in self.flasher.operations))

    def test_blank_board_install_uses_factory_image_at_zero(self):
        self.flasher.flash(self.manifest, "tqtpro", factory=True)
        self.assertEqual(self.flasher.operations, [("flash-id",), ("write-flash", "0x0"), ("verify-flash", "0x0")])

    def test_corrupt_image_is_rejected_before_opening_serial_port(self):
        (self.root / "test.app.bin").write_bytes(b"x" * len(self.app))
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.flasher.flash(self.manifest, "tqtpro")
        self.assertEqual(self.flasher.operations, [])

    def test_waveshare147_requires_16mb_and_updates_alternate_slot(self):
        manifest = json.loads(self.manifest.read_text())
        manifest["images"] = {"waveshare147": manifest["images"]["tqtpro"]}
        self.manifest.write_text(json.dumps(manifest))
        for wrong_size in (4, 8):
            self.flasher.flash_mb = wrong_size
            with self.assertRaisesRegex(ValueError, "16MB"):
                self.flasher.flash(self.manifest, "waveshare147", factory=True)
            self.assertFalse(any(op[0] == "write-flash" for op in self.flasher.operations))
        self.flasher.operations.clear()
        self.flasher.flash_mb = 16
        self.flasher.sequence = 1  # app0 selected: update must write app1 at 0x650000.
        self.flasher.flash(self.manifest, "waveshare147")
        writes = [op for op in self.flasher.operations if op[0] == "write-flash"]
        self.assertEqual(writes, [("write-flash", "0x650000"), ("write-flash", "0xf000")])
        self.assertLess(self.flasher.operations.index(("verify-flash", "0x650000")),
                        self.flasher.operations.index(("write-flash", "0xf000")))
