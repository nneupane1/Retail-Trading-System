import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from data.downloader import MarketDataDownloader


class DummyConfig:
    def require(self, *keys):
        if keys == ("app", "default_symbol"):
            return "BTCUSDT"
        if keys == ("binance", "default_interval"):
            return "1m"
        raise KeyError(keys)


class DummyClient:
    pass


class DownloaderCheckpointTests(unittest.TestCase):
    def test_checkpoint_replace_retries_after_transient_permission_error(self):
        downloader = MarketDataDownloader(config=DummyConfig(), client=DummyClient())

        with tempfile.TemporaryDirectory() as temp_dir:
            checkpoint_path = Path(temp_dir) / "checkpoint.json"
            replace_calls = {"count": 0}

            original_replace = Path.replace

            def flaky_replace(path_obj, target):
                if path_obj == checkpoint_path.with_suffix(".json.tmp"):
                    replace_calls["count"] += 1
                    if replace_calls["count"] == 1:
                        raise PermissionError("locked once")
                return original_replace(path_obj, target)

            with patch("data.downloader.Path.replace", new=flaky_replace):
                downloader._write_checkpoint(checkpoint_path, {"rows_downloaded": 123})

            self.assertEqual(replace_calls["count"], 2)
            self.assertTrue(checkpoint_path.exists())
            self.assertEqual(
                json.loads(checkpoint_path.read_text(encoding="utf-8")),
                {"rows_downloaded": 123},
            )


if __name__ == "__main__":
    unittest.main()
