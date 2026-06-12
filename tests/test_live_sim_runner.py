import tempfile
import unittest
from pathlib import Path

import pandas as pd

from live_sim.runner import (
    _discover_live_symbols,
    _load_live_bootstrap_history,
    _momentum_ranks,
    _merge_recent_into_state,
    _required_live_warmup_minutes,
    _runtime_state_path,
)


class DummyConfig:
    def __init__(self, storage_base_path):
        self.data = {
            "app": {
                "default_symbol": "BTCUSDT",
            },
            "binance": {
                "default_interval": "1m",
                "recent_limit": 1000,
            },
            "live_sim": {
                "poll_seconds": 30,
                "universe": {
                    "symbols": ["BTCUSDT", "ETHUSDT"],
                    "active_set": "current_9",
                },
            },
            "storage": {
                "base_path": storage_base_path,
            },
            "history": {
                "start_date": "2018-01-01",
                "end_date": "2026-05-12",
            },
            "downloads": {
                "history": {
                    "partial_suffix": ".partial.csv",
                },
            },
            "universe": {
                "active_set": "current_9",
                "symbol_sets": {
                    "current_9": ["BTCUSDT", "ETHUSDT"],
                    "expanded_liquid_28": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
                },
            },
            "features": {
                "ema_periods": {
                    "fast": 20,
                    "slow": 50,
                },
                "structure": {
                    "high_period": 20,
                    "low_period": 10,
                },
                "compression": {
                    "slow_range_period": 30,
                },
                "candle_metrics": {
                    "average_body_period": 10,
                },
            },
            "strategy": {
                "bias": {
                    "ema_column": "ema50",
                    "slope_lookback": 3,
                },
                "regime": {
                    "ema_column": "ema50",
                    "slope_lookback": 5,
                },
            },
            "timeframes": {
                "execution": {"rule": "15min"},
                "direction": {"rule": "1h"},
                "trend": {"rule": "5h"},
                "macro": {"rule": "12h"},
            },
        }

    def require(self, *keys):
        value = self.data
        for key in keys:
            value = value[key]
        return value

    def get(self, *keys, default=None):
        value = self.data
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value


class LiveSimRunnerTests(unittest.TestCase):
    def test_discover_live_symbols_uses_local_symbol_folders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "BTCUSDT").mkdir(parents=True, exist_ok=True)
            Path(temp_dir, "ETHUSDT").mkdir(parents=True, exist_ok=True)
            config = DummyConfig(storage_base_path=temp_dir)

            symbols = _discover_live_symbols(config)

            self.assertEqual(symbols, ["BTCUSDT", "ETHUSDT"])

    def test_discover_live_symbols_can_use_named_universe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=temp_dir)
            config.data["live_sim"]["universe"]["symbols"] = []
            config.data["live_sim"]["universe"]["active_set"] = "expanded_liquid_28"

            symbols = _discover_live_symbols(config)

            self.assertEqual(symbols, ["BTCUSDT", "ETHUSDT", "SOLUSDT"])

    def test_required_live_warmup_minutes_covers_macro_requirement(self):
        config = DummyConfig(storage_base_path="data_storage")

        warmup_minutes = _required_live_warmup_minutes(config)

        self.assertEqual(warmup_minutes, 46800)

    def test_merge_recent_into_state_deduplicates_and_keeps_latest_rows(self):
        index_existing = pd.to_datetime([
            "2026-01-01 00:00:00",
            "2026-01-01 00:01:00",
        ])
        existing = pd.DataFrame(
            {
                "open": [1, 2],
                "high": [1, 2],
                "low": [1, 2],
                "close": [1, 2],
                "volume": [10, 20],
            },
            index=index_existing,
        )

        index_recent = pd.to_datetime([
            "2026-01-01 00:01:00",
            "2026-01-01 00:02:00",
        ])
        recent = pd.DataFrame(
            {
                "open": [20, 30],
                "high": [20, 30],
                "low": [20, 30],
                "close": [20, 30],
                "volume": [200, 300],
            },
            index=index_recent,
        )

        merged = _merge_recent_into_state(existing, recent, warmup_minutes=60)

        self.assertEqual(len(merged), 3)
        self.assertEqual(merged.loc[pd.Timestamp("2026-01-01 00:01:00"), "close"], 20)
        self.assertEqual(merged.index[-1], pd.Timestamp("2026-01-01 00:02:00"))

    def test_load_live_bootstrap_history_prefers_final_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=temp_dir)
            folder = Path(temp_dir) / "BTCUSDT" / "1m"
            folder.mkdir(parents=True, exist_ok=True)

            final_path = folder / "BTCUSDT_1m_2018-01-01_to_2026-05-12.csv"
            partial_path = folder / "BTCUSDT_1m_2018-01-01_to_2026-05-12.csv.partial.csv"

            final_path.write_text(
                "timestamp,open,high,low,close,volume\n"
                "2026-01-01 00:00:00,1,1,1,1,1\n"
                "2026-01-01 00:01:00,2,2,2,2,2\n"
                "2026-01-01 00:02:00,3,3,3,3,3\n",
                encoding="utf-8",
            )
            partial_path.write_text(
                "timestamp,open,high,low,close,volume\n"
                "2026-01-01 00:00:00,9,9,9,9,9\n",
                encoding="utf-8",
            )

            df_1m, source_path = _load_live_bootstrap_history(
                symbol="BTCUSDT",
                interval="1m",
                warmup_minutes=60,
                config=config,
            )

            self.assertEqual(source_path, final_path)
            self.assertEqual(len(df_1m), 3)
            self.assertEqual(df_1m["close"].iloc[-1], 3)

    def test_load_live_bootstrap_history_falls_back_to_partial_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=temp_dir)
            folder = Path(temp_dir) / "BTCUSDT" / "1m"
            folder.mkdir(parents=True, exist_ok=True)

            partial_path = folder / "BTCUSDT_1m_2018-01-01_to_2026-05-12.csv.partial.csv"
            partial_path.write_text(
                "timestamp,open,high,low,close,volume\n"
                "2026-01-01 00:00:00,1,1,1,1,1\n"
                "2026-01-01 00:01:00,2,2,2,2,2\n",
                encoding="utf-8",
            )

            df_1m, source_path = _load_live_bootstrap_history(
                symbol="BTCUSDT",
                interval="1m",
                warmup_minutes=60,
                config=config,
            )

            self.assertEqual(source_path, partial_path)
            self.assertEqual(len(df_1m), 2)

    def test_load_live_bootstrap_history_can_use_timestamped_storage_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=temp_dir)
            folder = Path(temp_dir) / "BTCUSDT" / "1m"
            folder.mkdir(parents=True, exist_ok=True)

            timestamped = folder / (
                "BTCUSDT_1m_2018-01-01T00.00.00_to_2026-05-23T00.00.00.csv"
            )
            timestamped.write_text(
                "timestamp,open,high,low,close,volume\n"
                "2026-01-01 00:00:00,1,1,1,1,1\n"
                "2026-01-01 00:01:00,2,2,2,2,2\n",
                encoding="utf-8",
            )

            df_1m, source_path = _load_live_bootstrap_history(
                symbol="BTCUSDT",
                interval="1m",
                warmup_minutes=60,
                config=config,
            )

            self.assertEqual(source_path, timestamped)
            self.assertEqual(len(df_1m), 2)

    def test_load_live_bootstrap_history_accepts_later_starting_timestamped_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=temp_dir)
            folder = Path(temp_dir) / "SUIUSDT" / "1m"
            folder.mkdir(parents=True, exist_ok=True)

            timestamped = folder / (
                "SUIUSDT_1m_2023-05-01T00.00.00_to_2026-05-23T00.00.00.csv"
            )
            timestamped.write_text(
                "timestamp,open,high,low,close,volume\n"
                "2026-01-01 00:00:00,1,1,1,1,1\n"
                "2026-01-01 00:01:00,2,2,2,2,2\n",
                encoding="utf-8",
            )

            df_1m, source_path = _load_live_bootstrap_history(
                symbol="SUIUSDT",
                interval="1m",
                warmup_minutes=60,
                config=config,
            )

            self.assertEqual(source_path, timestamped)
            self.assertEqual(len(df_1m), 2)

    def test_load_live_bootstrap_history_prefers_runtime_state_when_present(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=temp_dir)
            folder = Path(temp_dir) / "BTCUSDT" / "1m"
            folder.mkdir(parents=True, exist_ok=True)

            final_path = folder / "BTCUSDT_1m_2018-01-01_to_2026-05-12.csv"
            final_path.write_text(
                "timestamp,open,high,low,close,volume\n"
                "2026-05-12 00:00:00,1,1,1,1,1\n"
                "2026-05-12 00:01:00,2,2,2,2,2\n",
                encoding="utf-8",
            )
            runtime_path = _runtime_state_path("BTCUSDT", "1m", config)
            runtime_path.write_text(
                "timestamp,open,high,low,close,volume\n"
                "2026-06-13 00:00:00,5,5,5,5,5\n"
                "2026-06-13 00:01:00,6,6,6,6,6\n",
                encoding="utf-8",
            )

            df_1m, source_path = _load_live_bootstrap_history(
                symbol="BTCUSDT",
                interval="1m",
                warmup_minutes=60 * 24 * 60,
                config=config,
            )

            self.assertEqual(source_path, runtime_path)
            self.assertEqual(df_1m.index[-1], pd.Timestamp("2026-06-13 00:01:00"))
            self.assertEqual(df_1m["close"].iloc[-1], 6)

    def test_momentum_ranks_prioritize_stronger_recent_symbols(self):
        dates = pd.date_range("2026-01-01", periods=5, freq="15min")
        frames = {
            "BTCUSDT": pd.DataFrame({"close": [100, 101, 102, 103, 104]}, index=dates),
            "ETHUSDT": pd.DataFrame({"close": [100, 100, 100, 100, 100]}, index=dates),
            "SOLUSDT": pd.DataFrame({"close": [100, 99, 98, 97, 96]}, index=dates),
        }

        ranks, top_symbols = _momentum_ranks(frames, lookback_bars=2)

        self.assertGreater(ranks["BTCUSDT"], ranks["ETHUSDT"])
        self.assertGreater(ranks["ETHUSDT"], ranks["SOLUSDT"])
        self.assertEqual(top_symbols[0], "BTCUSDT")


if __name__ == "__main__":
    unittest.main()
