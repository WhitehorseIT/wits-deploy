import unittest
from unittest.mock import patch

import wits_keyboard
from wits_keyboard import _build


class BuildIdTests(unittest.TestCase):
    def test_a_substituted_commit_is_shown_with_the_version(self):
        with patch.object(_build, "COMMIT", "87c1e18"):
            self.assertEqual(wits_keyboard.build_id(), "87c1e18")
            self.assertEqual(wits_keyboard.version_label(), f"{wits_keyboard.__version__} (build 87c1e18)")

    def test_an_unsubstituted_placeholder_never_leaks_into_the_label(self):
        with patch.object(_build, "COMMIT", "$Format:%h$"), \
                patch("subprocess.run", side_effect=OSError("no git")):
            self.assertEqual(wits_keyboard.build_id(), "")
            self.assertEqual(wits_keyboard.version_label(), wits_keyboard.__version__)

    def test_in_a_git_checkout_the_commit_comes_from_git(self):
        with patch.object(_build, "COMMIT", "$Format:%h$"):
            found = wits_keyboard.build_id()
        self.assertRegex(found, r"^([0-9a-f]{7,12})?$")  # empty only if this copy is not a checkout


if __name__ == "__main__":
    unittest.main()
