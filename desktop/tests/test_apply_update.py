import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "apply_update.py"


def load():
    spec = importlib.util.spec_from_file_location("apply_update", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@unittest.skipUnless(SCRIPT.is_file(), "apply_update.py not present (packaged tests)")
class ApplyUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.module = load()
        write(self.root / "wits_keyboard" / "app.py", "OLD app")
        write(self.root / "wits_keyboard" / "gone_in_new.py", "removed upstream")
        write(self.root / "run.py", "OLD run")
        write(self.root / "apply_update.py", "THE HELPER")           # never replaced
        write(self.root / ".venv" / "keep.txt", "environment")        # never replaced
        write(self.root / "logs" / "log.txt", "logs")
        write(self.root / ".update" / "staged" / "wits_keyboard" / "app.py", "NEW app")
        write(self.root / ".update" / "staged" / "run.py", "NEW run")
        write(self.root / ".update" / "staged" / "apply_update.py", "NOT COPIED")
        write(self.root / ".update" / "pending.json", json.dumps({"version": "0.2.0-dev25", "commit": "abcdef1234"}))

    def test_apply_swaps_the_new_files_in_and_keeps_the_old_ones_for_rollback(self):
        self.assertEqual(self.module.apply(self.root), 0)
        self.assertEqual((self.root / "wits_keyboard" / "app.py").read_text(), "NEW app")
        self.assertFalse((self.root / "wits_keyboard" / "gone_in_new.py").exists())  # files removed upstream go
        self.assertEqual((self.root / "run.py").read_text(), "NEW run")
        self.assertEqual((self.root / "apply_update.py").read_text(), "THE HELPER")
        self.assertEqual((self.root / ".venv" / "keep.txt").read_text(), "environment")
        self.assertEqual((self.root / "logs" / "log.txt").read_text(), "logs")
        self.assertEqual((self.root / ".update" / "previous" / "run.py").read_text(), "OLD run")
        self.assertTrue((self.root / ".update" / "unconfirmed").exists())
        self.assertFalse((self.root / ".update" / "pending.json").exists())
        self.assertFalse((self.root / ".update" / "staged").exists())

    def test_rollback_restores_exactly_the_previous_files(self):
        self.module.apply(self.root)
        self.assertEqual(self.module.rollback(self.root), 0)
        self.assertEqual((self.root / "wits_keyboard" / "app.py").read_text(), "OLD app")
        self.assertEqual((self.root / "wits_keyboard" / "gone_in_new.py").read_text(), "removed upstream")
        self.assertEqual((self.root / "run.py").read_text(), "OLD run")
        self.assertFalse((self.root / ".update" / "unconfirmed").exists())
        self.assertFalse((self.root / ".update" / "previous").exists())

    def test_a_failure_halfway_leaves_the_old_version_in_place(self):
        real_move = self.module._move
        calls = []

        def flaky(source, destination, attempts=4):
            calls.append(source.name)
            if len(calls) == 4:  # the 4th move is wits_keyboard's replacement or run.py's, after the first folder swapped
                raise OSError("file is locked")
            real_move(source, destination, attempts)

        with patch.object(self.module, "_move", flaky):
            self.assertEqual(self.module.apply(self.root), 1)
        self.assertEqual((self.root / "wits_keyboard" / "app.py").read_text(), "OLD app")
        self.assertEqual((self.root / "run.py").read_text(), "OLD run")
        self.assertFalse((self.root / ".update" / "unconfirmed").exists())

    def test_nothing_pending_is_not_an_error_and_changes_nothing(self):
        (self.root / ".update" / "pending.json").unlink()
        self.assertEqual(self.module.apply(self.root), 2)
        self.assertEqual((self.root / "run.py").read_text(), "OLD run")
        self.assertEqual(self.module.rollback(self.root), 2)  # no previous version either


if __name__ == "__main__":
    unittest.main()
