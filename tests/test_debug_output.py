import io
import unittest
from contextlib import redirect_stdout

from common.debug import configure_debug, debug_print, override_debug


class DummyConfig:
    def __init__(self, enabled):
        self.enabled = enabled

    def get(self, *keys, default=None):
        if keys == ("app", "debug"):
            return self.enabled
        return default


class DebugOutputTests(unittest.TestCase):
    def tearDown(self):
        configure_debug(enabled=True)

    def test_debug_print_is_suppressed_when_debug_is_disabled(self):
        configure_debug(config=DummyConfig(enabled=False))
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            debug_print("hidden")

        self.assertEqual(buffer.getvalue(), "")

    def test_debug_print_emits_when_debug_is_enabled(self):
        configure_debug(config=DummyConfig(enabled=True))
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            debug_print("visible")

        self.assertEqual(buffer.getvalue(), "visible\n")

    def test_override_debug_suppresses_output_even_when_enabled_in_config(self):
        configure_debug(config=DummyConfig(enabled=True))
        buffer = io.StringIO()

        with override_debug(False):
            with redirect_stdout(buffer):
                debug_print("hidden")

        self.assertEqual(buffer.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
