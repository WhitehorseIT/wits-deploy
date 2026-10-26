import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-docs.py"


def load():
    spec = importlib.util.spec_from_file_location("check_docs", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(SCRIPT.is_file(), "documentation checker not present (packaged tests)")
class DocumentationTests(unittest.TestCase):
    def test_documentation_matches_the_code(self):
        self.assertEqual(load().problems(), [])

    def test_the_checker_detects_the_problems_it_exists_for(self):
        module = load()
        self.assertEqual(module.slug("Windows (run from Python)"), "windows-run-from-python")
        self.assertEqual(module.slug("Firmware version colors and the update check"),
                         "firmware-version-colors-and-the-update-check")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "docs" / "release-notes").mkdir(parents=True)
            (root / "docs" / "boards").mkdir()
            (root / "src").mkdir()
            (root / "desktop" / "wits_keyboard").mkdir(parents=True)
            (root / "desktop" / "packaging").mkdir()
            (root / "src" / "firmware_version.h").write_text('constexpr char VERSION[] = "1.0.0";')
            (root / "desktop" / "wits_keyboard" / "__init__.py").write_text('__version__ = "1.0.1"')
            (root / "desktop" / "packaging" / "firmware-release.txt").write_text("1.0.0")
            readme = root / "README.md"
            readme.write_text("[gone](missing.md) [bad](docs/a.md#nope) WITS Keyboard")
            (root / "docs" / "a.md").write_text("# Real heading\n")
            (root / "docs" / "b.md").write_text("# Nobody links here\n")
            module.ROOT = root
            module.MARKDOWN = [readme, root / "docs" / "a.md"]
            found = "\n".join(module.problems())
        for expected in ("Version files disagree", "Missing release notes", "broken link missing.md",
                         "no heading for anchor docs/a.md#nope", "old product name",
                         "docs/b.md is not linked"):
            self.assertIn(expected, found)


if __name__ == "__main__":
    unittest.main()
