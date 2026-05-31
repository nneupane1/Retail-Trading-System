import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from backtest.edge_lab import (
    _resolve_base_history_file,
    export_edge_table_json,
    extract_edge_signals,
    summarize_edge_buckets,
    summarize_edge_frequency,
    summarize_edge_overview,
    summarize_edge_signals,
)
from config import AppConfig


class EdgeLabTests(unittest.TestCase):
    def test_resolve_base_history_file_can_use_timestamped_local_history(self):
        with TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            target = folder / "BTCUSDT_1m_2018-01-01T00.00.00_to_2026-05-23T00.00.00.csv"
            target.write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")

            resolved = _resolve_base_history_file(
                folder,
                "BTCUSDT",
                "1m",
                "2018-01-01",
                "2026-05-22",
            )

            self.assertEqual(resolved, target)

    def test_extract_edge_signals_isolates_refined_breakout_families(self):
        config = AppConfig.load()
        index = pd.date_range("2026-01-01 00:00:00", periods=9, freq="15min")
        df = pd.DataFrame(
            {
                "close": [100, 102, 105, 106, 104, 101, 103, 104, 105],
                "high": [101, 103, 106, 107, 105, 102, 104, 105, 106],
                "low": [99, 101, 104, 105, 103, 100, 102, 103, 104],
                "body_strength": [1.0, 1.3, 2.2, 1.1, 0.8, 1.3, 1.1, 1.0, 0.9],
                "close_position": [0.5, 0.72, 0.82, 0.62, 0.45, 0.78, 0.65, 0.58, 0.55],
                "compression": [False, True, False, False, False, True, False, False, False],
                "breakout": [False, True, True, False, False, True, False, False, False],
                "breakdown": [False, False, False, False, False, False, False, False, False],
                "vwap_distance_ratio": [0.0, 0.002, 0.003, 0.002, 0.001, 0.002, 0.003, 0.001, 0.0],
                "upper_wick_ratio": [0.5, 0.4, 0.3, 0.5, 0.6, 0.4, 0.3, 0.4, 0.5],
                "lower_wick_ratio": [0.5, 0.4, 0.3, 0.5, 0.6, 0.4, 0.3, 0.4, 0.5],
                "atr_rising": [False, True, True, True, False, True, True, False, False],
                "prev_close": [0, 100, 102, 105, 106, 104, 101, 103, 104],
            },
            index=index,
        )

        signals = extract_edge_signals(
            df,
            symbol="BTCUSDT",
            horizons=(1, 3),
            round_trip_fee_rate=0.001,
            config=config,
        )

        families = set(signals["edge_family"].unique())
        self.assertIn("impulse_breakout", families)
        self.assertIn("pressure_breakout", families)
        self.assertIn("breakout_pullback", families)
        self.assertIn("edge_type", signals.columns)
        self.assertIn("bias_bucket", signals.columns)
        self.assertIn("body_bucket", signals.columns)
        self.assertIn("vwap_bucket", signals.columns)
        self.assertTrue((signals["future_return_net"] <= signals["future_return_gross"]).all())

    def test_edge_summaries_capture_frequency_and_expectancy(self):
        signals = pd.DataFrame(
            {
                "symbol": ["BTCUSDT", "BTCUSDT", "ETHUSDT"],
                "timestamp": pd.to_datetime(
                    ["2026-01-01 00:00:00", "2026-01-01 00:15:00", "2026-01-02 00:00:00"]
                ),
                "edge_family": ["impulse_breakout", "impulse_breakout", "pressure_breakout"],
                "side": ["long", "long", "long"],
                "horizon_candles": [1, 1, 3],
                "future_return_gross": [0.01, -0.002, 0.008],
                "future_return_net": [0.009, -0.003, 0.007],
                "future_range_ratio": [0.02, 0.01, 0.03],
                "favorable_excursion": [0.015, 0.004, 0.012],
                "adverse_excursion": [-0.004, -0.006, -0.005],
                "vwap_reversion_ratio": [0.1, -0.05, 0.2],
                "edge_type": ["impulse_breakout", "impulse_breakout", "pressure_breakout"],
                "bias_bucket": ["bullish", "bullish", "neutral"],
                "body_bucket": ["strong", "strong", "weak"],
                "vwap_bucket": ["near", "near", "far"],
            }
        )

        summary = summarize_edge_signals(signals)
        frequency = summarize_edge_frequency(signals)
        overview = summarize_edge_overview(signals)

        momentum_row = summary[summary["edge_family"] == "impulse_breakout"].iloc[0]
        self.assertEqual(int(momentum_row["signal_count"]), 2)
        self.assertAlmostEqual(float(momentum_row["win_rate_net"]), 0.5)
        self.assertEqual(len(frequency), 2)
        self.assertEqual(int(overview.loc[0, "signal_count"]), 3)
        self.assertGreater(float(overview.loc[0, "avg_signals_per_day"]), 0.0)

    def test_edge_bucket_summary_and_json_export_remain_small_and_actionable(self):
        signals = pd.DataFrame(
            {
                "edge_type": ["impulse_breakout"] * 4 + ["pressure_breakout"] * 2,
                "bias_bucket": ["bullish"] * 4 + ["bullish"] * 2,
                "body_bucket": ["strong"] * 6,
                "vwap_bucket": ["near"] * 4 + ["near"] * 2,
                "horizon_candles": [1, 1, 3, 3, 1, 1],
                "future_return_gross": [0.003, 0.002, 0.004, 0.003, -0.001, -0.002],
                "future_return_net": [0.002, 0.001, 0.003, 0.002, -0.002, -0.003],
            }
        )

        bucket_summary = summarize_edge_buckets(
            signals,
            min_count=2,
            min_avg_return_net=0.0,
        )
        valid_row = bucket_summary[bucket_summary["edge_type"] == "impulse_breakout"].iloc[0]
        invalid_row = bucket_summary[bucket_summary["edge_type"] == "pressure_breakout"].iloc[0]

        self.assertTrue(bool(valid_row["valid"]))
        self.assertGreater(float(valid_row["risk_mult"]), 1.0)
        self.assertFalse(bool(invalid_row["valid"]))

        with TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "edge_table.json"
            export_edge_table_json(
                bucket_summary,
                target,
                min_count=2,
                min_avg_return_net=0.0,
            )
            self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()
