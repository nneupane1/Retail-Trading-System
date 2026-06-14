import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

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


class FetchHistoryConfig:
    def __init__(self, base_path):
        self.base_path = base_path

    def require(self, *keys):
        if keys == ("app", "default_symbol"):
            return "BTCUSDT"
        if keys == ("binance", "default_interval"):
            return "1m"
        if keys == ("history", "start_date"):
            return "2026-05-12"
        if keys == ("history", "end_date"):
            return "2026-05-13"
        if keys == ("storage", "base_path"):
            return self.base_path
        if keys == ("binance", "historical_limit"):
            return 1000
        if keys == ("binance", "throttle_seconds"):
            return 0
        if keys == ("binance", "closed_klines_only"):
            return True
        if keys == ("downloads", "history"):
            return {
                "checkpoint_dir": "_checkpoints",
                "checkpoint_suffix": ".checkpoint.json",
                "partial_suffix": ".partial.csv",
                "resume_enabled": True,
                "save_every_batches": 1,
                "status_every_batches": 1,
                "cleanup_partial_on_complete": True,
            }
        raise KeyError(keys)


class FetchHistoryClient:
    def __init__(self, raw_batch):
        self.raw_batch = raw_batch
        self.calls = []
        self.retry_callback = None

    def describe_verify_mode(self):
        return "disabled"

    def get_klines(self, **kwargs):
        self.calls.append(kwargs)
        return self.raw_batch


class NullDisplay:
    enabled = False

    def start(self, **kwargs):
        return None

    def stop(self):
        return None


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

    def test_fetch_full_history_bootstraps_extended_range_from_existing_final_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)
            storage_dir = base_path / "BTCUSDT" / "1m"
            storage_dir.mkdir(parents=True, exist_ok=True)

            existing_final = storage_dir / "BTCUSDT_1m_2026-05-12_to_2026-05-12.csv"
            existing_df = pd.DataFrame(
                [
                    {
                        "timestamp": "2026-05-12 23:58:00",
                        "open": 100.0,
                        "high": 101.0,
                        "low": 99.5,
                        "close": 100.5,
                        "volume": 10.0,
                    },
                    {
                        "timestamp": "2026-05-12 23:59:00",
                        "open": 100.5,
                        "high": 101.5,
                        "low": 100.0,
                        "close": 101.0,
                        "volume": 12.0,
                    },
                ]
            )
            existing_df.to_csv(existing_final, index=False)

            next_open_time = int(
                pd.Timestamp("2026-05-13 00:00:00", tz="UTC").timestamp() * 1000
            )
            next_close_time = next_open_time + 59999
            raw_batch = [[
                next_open_time,
                "101.0",
                "102.0",
                "100.5",
                "101.5",
                "9.0",
                next_close_time,
                "0",
                "0",
                "0",
                "0",
                "0",
            ]]

            client = FetchHistoryClient(raw_batch=raw_batch)
            downloader = MarketDataDownloader(
                config=FetchHistoryConfig(str(base_path)),
                client=client
            )

            with patch("data.downloader.DownloadProgressDisplay", return_value=NullDisplay()):
                df = downloader.fetch_full_history()

            expected_resume_start = int(
                pd.Timestamp("2026-05-12 23:59:00", tz="UTC").timestamp() * 1000
            ) + 1

            self.assertEqual(client.calls[0]["startTime"], expected_resume_start)
            self.assertEqual(len(df), 3)
            self.assertEqual(
                pd.Timestamp(df.index[-1]),
                pd.Timestamp("2026-05-13 00:00:00")
            )
            self.assertTrue(
                (storage_dir / "BTCUSDT_1m_2026-05-12_to_2026-05-13.csv").exists()
            )

    def test_fetch_full_history_bootstraps_from_timestamped_cached_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)
            storage_dir = base_path / "BTCUSDT" / "1m"
            storage_dir.mkdir(parents=True, exist_ok=True)

            existing_final = storage_dir / "BTCUSDT_1m_2026-05-12T00.00.00_to_2026-05-12T00.00.00.csv"
            existing_df = pd.DataFrame(
                [
                    {
                        "timestamp": "2026-05-12 23:58:00",
                        "open": 100.0,
                        "high": 101.0,
                        "low": 99.5,
                        "close": 100.5,
                        "volume": 10.0,
                    },
                    {
                        "timestamp": "2026-05-12 23:59:00",
                        "open": 100.5,
                        "high": 101.5,
                        "low": 100.0,
                        "close": 101.0,
                        "volume": 12.0,
                    },
                ]
            )
            existing_df.to_csv(existing_final, index=False)

            next_open_time = int(
                pd.Timestamp("2026-05-13 00:00:00", tz="UTC").timestamp() * 1000
            )
            next_close_time = next_open_time + 59999
            raw_batch = [[
                next_open_time,
                "101.0",
                "102.0",
                "100.5",
                "101.5",
                "9.0",
                next_close_time,
                "0",
                "0",
                "0",
                "0",
                "0",
            ]]

            client = FetchHistoryClient(raw_batch=raw_batch)
            downloader = MarketDataDownloader(
                config=FetchHistoryConfig(str(base_path)),
                client=client
            )

            with patch("data.downloader.DownloadProgressDisplay", return_value=NullDisplay()):
                df = downloader.fetch_full_history()

            expected_resume_start = int(
                pd.Timestamp("2026-05-12 23:59:00", tz="UTC").timestamp() * 1000
            ) + 1

            self.assertEqual(client.calls[0]["startTime"], expected_resume_start)
            self.assertEqual(len(df), 3)
            self.assertTrue(
                (storage_dir / "BTCUSDT_1m_2026-05-12_to_2026-05-13.csv").exists()
            )


if __name__ == "__main__":
    unittest.main()
