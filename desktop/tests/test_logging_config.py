import logging
import unittest

from wits_keyboard.logging_config import PayloadRedactionFilter, safe_error


class LoggingSafetyTests(unittest.TestCase):
    def test_empty_timeout_has_useful_message(self):
        self.assertEqual(safe_error(TimeoutError()), "operation timed out")

    def test_bleak_write_payload_is_redacted(self):
        record = logging.LogRecord(
            "bleak.backends.bluezdbus.client",
            logging.DEBUG,
            __file__,
            1,
            "Write Characteristic %s: %s",
            ("uuid", bytearray(b"do-not-log-this")),
            None,
        )
        self.assertTrue(PayloadRedactionFilter().filter(record))
        self.assertNotIn("do-not-log-this", record.getMessage())
        self.assertIn("payload omitted", record.getMessage())

    def test_write_failure_error_is_redacted(self):
        error = RuntimeError(
            "Could not write value bytearray(b'do-not-log-this') to characteristic"
        )
        message = safe_error(error)
        self.assertNotIn("do-not-log-this", message)
        self.assertIn("payload omitted", message)


if __name__ == "__main__":
    unittest.main()
