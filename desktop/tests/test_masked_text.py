import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication
    from wits_keyboard.app import MaskedPlainTextEdit
    QT = True
except ImportError:
    QT = False


@unittest.skipUnless(QT, "Qt not installed")
class MaskedTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make(self, text):
        editor = MaskedPlainTextEdit()
        editor.resize(420, 120)
        editor.show()
        editor.setPlainText(text)
        self.app.processEvents()
        return editor

    @staticmethod
    def dark_pixels(editor):
        """Pixels inside the text area (not the frame) that differ from the background."""
        image = editor.grab().toImage()
        area = editor.viewport().geometry().adjusted(2, 2, -2, -2)
        background = image.pixelColor(area.left(), area.bottom())
        count = 0
        for y in range(area.top(), area.bottom() + 1):
            for x in range(area.left(), area.right() + 1):
                if image.pixelColor(x, y) != background:
                    count += 1
        return count

    def test_hidden_text_is_shown_as_bullets_but_the_real_text_is_kept(self):
        editor = self.make("hunter2\nsecond line")
        editor.set_masked(True)
        self.app.processEvents()
        self.assertEqual(editor.toPlainText(), "hunter2\nsecond line")  # what gets sent is untouched
        self.assertTrue(editor.masked)
        self.assertGreater(self.dark_pixels(editor), 50)  # bullets were drawn, not a blank box

    def test_an_empty_hidden_box_draws_nothing_and_showing_again_restores_the_font(self):
        editor = self.make("")
        normal_family = editor.font().family()
        plain_empty = self.dark_pixels(editor)  # just the caret
        editor.set_masked(True)
        self.app.processEvents()
        self.assertLessEqual(self.dark_pixels(editor), plain_empty + 2)
        editor.set_masked(False)
        self.assertEqual(editor.font().family(), normal_family)
        self.assertFalse(editor.masked)

    def test_more_characters_mean_more_bullets(self):
        short, long = self.make("ab"), self.make("abcdefghijklmnop")
        for editor in (short, long):
            editor.set_masked(True)
            self.app.processEvents()
        self.assertGreater(self.dark_pixels(long), self.dark_pixels(short))

    def test_the_masked_text_does_not_show_through(self):
        editor = self.make("MMMMMMMM")
        editor.set_masked(True)
        self.app.processEvents()
        masked = self.dark_pixels(editor)
        editor.set_masked(False)
        self.app.processEvents()
        self.assertNotEqual(masked, self.dark_pixels(editor))  # bullets differ from the letters


if __name__ == "__main__":
    unittest.main()
