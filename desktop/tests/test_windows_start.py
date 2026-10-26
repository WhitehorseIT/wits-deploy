import re
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "WINDOWS-START.cmd"


@unittest.skipUnless(SCRIPT.is_file(), "launcher not present (packaged tests)")
class WindowsStartScriptTests(unittest.TestCase):
    def setUp(self):
        self.text = SCRIPT.read_text()
        self.labels = set(re.findall(r"^:([a-z_]+)\s*$", self.text, re.M))

    def test_every_goto_has_a_matching_label(self):
        targets = set(re.findall(r"goto ([a-z_]+)", self.text))
        self.assertTrue(targets)
        self.assertEqual(targets - self.labels, set())

    def test_it_checks_python_packages_then_starts_the_app(self):
        order = [self.text.index("where py"), self.text.index("-m venv"),
                 self.text.index("-m pip install -r requirements-release.txt"),
                 self.text.rindex('python.exe" run.py')]
        self.assertEqual(order, sorted(order))
        for needed in ("requirements-release.txt", "import PySide6", "py -3", "pause"):
            self.assertIn(needed, self.text)

    def test_old_launcher_names_are_gone(self):
        root = SCRIPT.parent
        self.assertFalse((root / "desktop" / "SETUP-WINDOWS.cmd").exists())
        self.assertFalse((root / "desktop" / "START-WINDOWS.cmd").exists())

    def test_it_asks_for_extraction_when_files_are_missing(self):
        self.assertIn(":not_extracted", self.text)
        self.assertIn("Extract All", self.text)


if __name__ == "__main__":
    unittest.main()
