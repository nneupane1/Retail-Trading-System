import unittest
from unittest.mock import patch

import common.download_progress as download_progress


class _FakeProgress:
    def add_task(self, *args, **kwargs):
        return 1

    def update(self, *args, **kwargs):
        return None


class _FailingLiveStart:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        raise UnicodeEncodeError("charmap", "\u280b", 0, 1, "character maps to <undefined>")

    def stop(self):
        return None


class _FailingLiveUpdate:
    def __init__(self):
        self.stopped = False

    def update(self, *args, **kwargs):
        raise UnicodeEncodeError("charmap", "\u280b", 0, 1, "character maps to <undefined>")

    def stop(self):
        self.stopped = True


class DownloadProgressDisplayTests(unittest.TestCase):
    def test_start_disables_rich_when_console_cannot_encode_spinner(self):
        display = download_progress.DownloadProgressDisplay(enabled=True)
        display.enabled = True

        with patch.object(download_progress, "Progress", return_value=_FakeProgress()), \
             patch.object(download_progress, "Live", _FailingLiveStart), \
             patch.object(display, "_build_renderable", return_value=object()):
            display.start(
                symbol="BTCUSDT",
                interval="1m",
                start_date="2026-01-01",
                end_date="2026-01-02",
                final_path="final.csv",
                checkpoint_path="checkpoint.json",
            )

        self.assertFalse(display.enabled)
        self.assertIsNone(display.live)
        self.assertIsNone(display.progress)

    def test_refresh_disables_rich_when_console_update_fails(self):
        display = download_progress.DownloadProgressDisplay(enabled=True)
        display.enabled = True
        display.live = _FailingLiveUpdate()

        with patch.object(display, "_build_renderable", return_value=object()):
            display.refresh()

        self.assertFalse(display.enabled)
        self.assertIsNone(display.live)
        self.assertIsNone(display.progress)


if __name__ == "__main__":
    unittest.main()
