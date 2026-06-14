import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from backtest.window_policy import (
    resolve_full_history_window,
    resolve_trailing_12m_holdout_window,
    resolve_latest_common_data_timestamp,
    write_validation_window_artifact,
)
from config import AppConfig


class ValidationWindowPolicyTests(unittest.TestCase):
    def _make_config(self, temp_dir: str) -> AppConfig:
        return AppConfig(
            data={
                "history": {
                    "start_date": "2018-01-01",
                    "end_date": "2026-06-12",
                },
                "binance": {
                    "default_interval": "1m",
                },
                "backtest": {
                    "portfolio_replay": {
                        "symbols": ["BTCUSDT", "ETHUSDT"],
                    }
                },
            },
            config_path=Path(temp_dir) / "settings.json",
            root_dir=Path(temp_dir),
        )

    def test_resolve_latest_common_data_timestamp_uses_min_symbol_timestamp(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._make_config(temp_dir)

            def fake_load(symbol, interval, config):
                index = pd.to_datetime(
                    ["2026-06-10 23:59:00", "2026-06-11 23:59:00"]
                    if symbol == "BTCUSDT"
                    else ["2026-06-09 23:59:00", "2026-06-10 23:59:00"],
                    utc=True,
                )
                frame = pd.DataFrame(
                    {
                        "open": [1.0, 1.0],
                        "high": [1.0, 1.0],
                        "low": [1.0, 1.0],
                        "close": [1.0, 1.0],
                        "volume": [1.0, 1.0],
                    },
                    index=index,
                )
                return frame, Path(temp_dir) / f"{symbol}.csv"

            with patch("backtest.window_policy._load_full_history", side_effect=fake_load):
                latest_common, rows = resolve_latest_common_data_timestamp(config)

        self.assertEqual(latest_common.isoformat(), "2026-06-10T23:59:00+00:00")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["symbol"], "BTCUSDT")
        self.assertEqual(rows[1]["symbol"], "ETHUSDT")

    def test_resolve_full_history_window_includes_latest_closed_day_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._make_config(temp_dir)

            with patch(
                "backtest.window_policy.resolve_latest_common_data_timestamp",
                return_value=(
                    pd.Timestamp("2026-06-12 23:59:00", tz="UTC"),
                    [{"symbol": "BTCUSDT", "latest_timestamp": "2026-06-12T23:59:00+00:00"}],
                ),
            ):
                metadata = resolve_full_history_window(config, symbols=["BTCUSDT"])

        self.assertEqual(metadata.window_policy, "full_history_latest_closed_day_v1")
        self.assertEqual(metadata.train_start, "2018-01-01")
        self.assertEqual(metadata.train_end, "2026-06-12")
        self.assertIsNone(metadata.holdout_start)
        self.assertIsNone(metadata.holdout_end)
        self.assertEqual(metadata.latest_data_timestamp, "2026-06-12T23:59:00+00:00")

    def test_resolve_trailing_12m_holdout_window_builds_non_overlapping_boundaries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._make_config(temp_dir)

            with patch(
                "backtest.window_policy.resolve_latest_common_data_timestamp",
                return_value=(
                    pd.Timestamp("2026-06-12 23:59:00", tz="UTC"),
                    [{"symbol": "BTCUSDT", "latest_timestamp": "2026-06-12T23:59:00+00:00"}],
                ),
            ):
                metadata = resolve_trailing_12m_holdout_window(config, symbols=["BTCUSDT"])

        self.assertEqual(metadata.window_policy, "trailing_12m_unseen_holdout_v1")
        self.assertEqual(metadata.train_start, "2018-01-01")
        self.assertEqual(metadata.train_end, "2025-06-12")
        self.assertEqual(metadata.holdout_start, "2025-06-13")
        self.assertEqual(metadata.holdout_end, "2026-06-12")
        self.assertEqual(metadata.latest_data_timestamp, "2026-06-12T23:59:00+00:00")

    def test_write_validation_window_artifact_persists_required_fields(self):
        payload = {
            "window_policy": "trailing_12m_unseen_holdout_v1",
            "train_start": "2018-01-01",
            "train_end": "2025-06-12",
            "holdout_start": "2025-06-13",
            "holdout_end": "2026-06-12",
            "latest_data_timestamp": "2026-06-12T23:59:00+00:00",
            "resolved_at_utc": "2026-06-13T00:00:00+00:00",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_validation_window_artifact(temp_dir, payload)
            loaded = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(loaded["train_start"], "2018-01-01")
        self.assertEqual(loaded["train_end"], "2025-06-12")
        self.assertEqual(loaded["holdout_start"], "2025-06-13")
        self.assertEqual(loaded["holdout_end"], "2026-06-12")
        self.assertEqual(loaded["latest_data_timestamp"], "2026-06-12T23:59:00+00:00")
        self.assertEqual(loaded["resolved_at_utc"], "2026-06-13T00:00:00+00:00")
        self.assertEqual(loaded["window_policy"], "trailing_12m_unseen_holdout_v1")


if __name__ == "__main__":
    unittest.main()
