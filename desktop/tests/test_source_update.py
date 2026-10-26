import hashlib
import io
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from wits_keyboard import source_update
from wits_keyboard.online_release import SignedRelease
from wits_keyboard.signing import SignatureError


def archive_bytes(members=None, top="wits-deploy-abcdef1"):
    members = members if members is not None else {
        "desktop/wits_keyboard/__init__.py": "NEW", "desktop/run.py": "NEW run",
        "desktop/requirements-release.txt": "pkg", "desktop/README.md": "readme",
        "docs/guide.md": "not extracted", "WINDOWS-START.cmd": "not extracted",
        "desktop/.venv/evil.txt": "skipped", "desktop/logs/x.log": "skipped"}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        for name, data in members.items():
            z.writestr(f"{top}/{name}" if top else name, data)
    return stream.getvalue()


def release_for(data, kind="source", commit="abcdef1234", sequence=3, version="0.2.0-dev25"):
    return SignedRelease(version, None, {"source": {"name": "WITS-Deploy-source.zip", "size": len(data),
                                                    "sha256": hashlib.sha256(data).hexdigest()}},
                         kind, commit, sequence)


class Net:
    def __init__(self, release, body):
        self.url, self.body = release.asset_url("source"), body

    def __call__(self, request, timeout=0):
        assert request.full_url == self.url, request.full_url
        stream = io.BytesIO(self.body)
        stream.__enter__ = lambda *a: stream
        stream.__exit__ = lambda *a: None
        return stream


class StageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def stage(self, data, body=None, **kwargs):
        release = release_for(data)
        return source_update.stage(source_update.Choice(release, "snapshot", "x"),
                                   urlopen=Net(release, data if body is None else body), root=self.root, **kwargs)

    def test_only_the_desktop_folder_is_unpacked_and_the_update_is_recorded(self):
        info = self.stage(archive_bytes())
        staged = self.root / ".update" / "staged"
        self.assertEqual((staged / "run.py").read_text(), "NEW run")
        self.assertTrue((staged / "wits_keyboard" / "__init__.py").is_file())
        self.assertFalse((staged / "docs").exists())
        self.assertFalse((staged / ".venv").exists())      # an archive can never overwrite the environment...
        self.assertFalse((staged / "logs").exists())       # ...or the logs
        self.assertEqual(json.loads((self.root / ".update" / "pending.json").read_text())["commit"], "abcdef1234")
        self.assertEqual(info["channel"], "snapshot")
        self.assertFalse((self.root / ".update" / "download.zip").exists())

    def test_a_tampered_download_is_refused_and_nothing_is_left_staged(self):
        with self.assertRaises(SignatureError):
            self.stage(archive_bytes(), body=archive_bytes({"desktop/run.py": "evil"}))
        self.assertFalse((self.root / ".update" / "staged").exists())
        self.assertFalse((self.root / ".update" / "pending.json").exists())

    def test_unsafe_paths_and_incomplete_archives_are_refused(self):
        for members in ({"desktop/../escape.py": "x", "desktop/run.py": "x"},
                        {"desktop/run.py": "only one file"}):
            with self.subTest(members=list(members)):
                with self.assertRaises(SignatureError):
                    self.stage(archive_bytes(members))
                self.assertFalse((self.root / ".update" / "staged").exists())
        self.assertFalse((self.root.parent / "escape.py").exists())

    def test_an_archive_with_several_top_level_folders_is_refused(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as z:
            z.writestr("one/desktop/run.py", "x")
            z.writestr("two/desktop/run.py", "x")
        with self.assertRaises(SignatureError):
            self.stage(stream.getvalue())

    def test_cancel_stops_the_download_and_leaves_nothing(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(InterruptedError):
            self.stage(archive_bytes(), cancelled=event)
        self.assertFalse((self.root / ".update" / "staged").exists())

    def test_confirming_a_healthy_start_clears_the_rollback_marker_and_the_saved_files(self):
        update = self.root / ".update"
        (update / "previous").mkdir(parents=True)
        (update / "unconfirmed").write_text("x")
        (update / "applied.json").write_text(json.dumps({"version": "0.2.0-dev25", "commit": "abcdef1234"}))
        note = source_update.confirm_started(self.root)
        self.assertIn("0.2.0-dev25 abcdef1", note)
        self.assertFalse((update / "unconfirmed").exists())
        self.assertFalse((update / "previous").exists())
        self.assertIsNone(source_update.confirm_started(self.root))  # nothing waiting the second time

    def test_a_rollback_is_reported_once(self):
        update = self.root / ".update"
        update.mkdir()
        (update / "rolled-back").write_text("x")
        self.assertIn("restored", source_update.rolled_back_note(self.root))
        self.assertIsNone(source_update.rolled_back_note(self.root))


class ChoiceTests(unittest.TestCase):
    def snapshot(self, commit="abcdef1234"):
        return release_for(b"x", commit=commit)

    def release(self, version, with_source=True):
        data = b"x"
        rel = release_for(data, kind="app", version=version, commit=None)
        return rel if with_source else SignedRelease(version, None, {"linux-x86_64": {}}, "app")

    def test_a_snapshot_is_offered_only_when_opted_in_and_different_from_this_build(self):
        snap = self.snapshot("abcdef1234")
        self.assertEqual(source_update.choose(None, snap, True, "0.2.0-dev24", "1234567").label, "snapshot")
        self.assertIsNone(source_update.choose(None, snap, False, "0.2.0-dev24", "1234567"))   # not opted in
        self.assertIsNone(source_update.choose(None, snap, True, "0.2.0-dev24", "abcdef1"))     # already on it
        self.assertEqual(source_update.choose(None, snap, True, "0.2.0-dev24", "").label, "snapshot")  # build unknown

    def test_a_newer_release_with_a_source_archive_is_offered_otherwise(self):
        choice = source_update.choose(self.release("0.2.0-dev25"), None, False, "0.2.0-dev24", "")
        self.assertEqual((choice.label, choice.release.version), ("release", "0.2.0-dev25"))
        self.assertIsNone(source_update.choose(self.release("0.2.0-dev24"), None, False, "0.2.0-dev24", ""))
        self.assertIsNone(source_update.choose(self.release("0.2.0-dev25", with_source=False), None, False,
                                               "0.2.0-dev24", ""))
        self.assertEqual(source_update.choose(self.release("0.2.0-dev25"), self.snapshot("ffff000"), True,
                                              "0.2.0-dev24", "1234567").label, "snapshot")  # opted in prefers the snapshot


class AvailabilityTests(unittest.TestCase):
    def test_reasons(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with patch.object(source_update, "frozen", return_value=True):
                self.assertIn("packaged", source_update.unavailable_reason(root))
            with patch.object(source_update, "frozen", return_value=False), patch.dict("os.environ", {}, clear=False):
                import os
                os.environ.pop(source_update.LAUNCHER_ENV, None)
                self.assertIn("WINDOWS-START.cmd", source_update.unavailable_reason(root))
                os.environ[source_update.LAUNCHER_ENV] = source_update.LAUNCHER_NAME
                self.assertIn("apply_update.py", source_update.unavailable_reason(root))
                (root / "apply_update.py").write_text("x")
                self.assertIsNone(source_update.unavailable_reason(root))
                os.environ.pop(source_update.LAUNCHER_ENV, None)


if __name__ == "__main__":
    unittest.main()
