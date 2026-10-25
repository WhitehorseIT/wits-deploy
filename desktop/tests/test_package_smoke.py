import subprocess
import unittest
from unittest.mock import patch

from wits_keyboard import package_smoke


def completed(code, text):
    return subprocess.CompletedProcess(["esptool"], code, stdout=text)


class EsptoolHelpTests(unittest.TestCase):
    def test_returns_exit_code_and_text_and_tolerates_missing_output(self):
        with patch.object(package_smoke.subprocess, "run", return_value=completed(0, None)):
            self.assertEqual(package_smoke.esptool_help(), (0, ""))
        with patch.object(package_smoke.subprocess, "run", return_value=completed(1, "usage: write-flash")):
            self.assertEqual(package_smoke.esptool_help(), (1, "usage: write-flash"))

    def test_flasher_style_call_closes_stdin_and_merges_error_output(self):
        with patch.object(package_smoke.subprocess, "run", return_value=completed(0, "ok")) as run:
            package_smoke.esptool_help()
        options = run.call_args.kwargs
        self.assertIs(options["stdin"], subprocess.DEVNULL)
        self.assertIs(options["stderr"], subprocess.STDOUT)

    def test_diagnostics_report_every_variant_even_when_one_fails(self):
        results = [completed(0, ""), RuntimeError("boom"), completed(0, "x" * 200), completed(0, ""), completed(0, "1.0")]
        with patch.object(package_smoke.subprocess, "run", side_effect=results):
            report = package_smoke.esptool_diagnostics()
        self.assertEqual(set(report), {"flasher-style", "inherited-stdin", "no-color", "utf8", "version-command"})
        self.assertEqual(report["inherited-stdin"], {"error": "boom"})
        self.assertEqual(report["no-color"]["characters"], 200)
        self.assertEqual(len(report["no-color"]["start"]), 80)


if __name__ == "__main__":
    unittest.main()
