import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backtest.validate_h6_holdout import _classify_training_symbols
from backtest.validate_h6_moonshot import _simulate_h6_trade, _write_reports


class DummyEngine:
    max_hold_6h_candles = 2


class ValidateH6MoonshotTests(unittest.TestCase):
    def test_classify_training_symbols_marks_keep_when_symbol_is_positive_and_active(self):
        summary_df = pd.DataFrame(
            [
                {
                    "symbol": "BNBUSDT",
                    "trade_count": 10,
                    "net_R": 5.0,
                    "avg_R": 0.5,
                    "median_R": 0.2,
                    "max_R": 2.0,
                    "win_rate": 0.6,
                    "hit_1R_rate": 0.5,
                    "hit_2R_rate": 0.3,
                },
                {
                    "symbol": "BTCUSDT",
                    "trade_count": 10,
                    "net_R": -1.0,
                    "avg_R": -0.1,
                    "median_R": -0.2,
                    "max_R": 0.5,
                    "win_rate": 0.4,
                    "hit_1R_rate": 0.2,
                    "hit_2R_rate": 0.1,
                },
            ]
        )
        events_df = pd.DataFrame(
            [
                {"symbol": "BNBUSDT", "realized_R": 2.0},
                {"symbol": "BNBUSDT", "realized_R": 3.0},
                {"symbol": "BTCUSDT", "realized_R": -0.5},
                {"symbol": "BTCUSDT", "realized_R": -0.5},
            ]
        )

        rows = _classify_training_symbols(summary_df, events_df)
        by_symbol = {row["symbol"]: row for row in rows}
        self.assertEqual("keep", by_symbol["BNBUSDT"]["status"])
        self.assertEqual("drop", by_symbol["BTCUSDT"]["status"])

    def test_simulate_h6_trade_stops_out_on_first_stop_touch(self):
        index = pd.to_datetime(
            [
                "2026-01-01 00:00:00",
                "2026-01-01 00:15:00",
                "2026-01-01 00:30:00",
            ]
        )
        execution = pd.DataFrame(
            {
                "open": [100.0, 100.0, 99.0],
                "high": [101.0, 100.5, 99.5],
                "low": [99.0, 97.9, 98.5],
                "close": [100.0, 98.5, 99.0],
                "volume": [10.0, 10.0, 10.0],
            },
            index=index,
        )
        row = _simulate_h6_trade(
            symbol="BTCUSDT",
            timestamp=index[0],
            execution_row=execution.iloc[0],
            snapshot={"h6_stop_long": 98.0, "signal_family_long": "h6_bridge_breakout"},
            execution_frame=execution,
            engine=DummyEngine(),
        )

        self.assertIsNotNone(row)
        self.assertEqual("stop", row["exit_reason"])
        self.assertEqual(-1.0, row["realized_R"])
        self.assertFalse(row["hit_2R"])

    def test_simulate_h6_trade_time_exits_when_stop_not_hit(self):
        index = pd.to_datetime(
            [
                "2026-01-01 00:00:00",
                "2026-01-01 00:15:00",
                "2026-01-01 00:30:00",
            ]
        )
        execution = pd.DataFrame(
            {
                "open": [100.0, 100.0, 101.0],
                "high": [100.5, 101.5, 104.5],
                "low": [99.5, 99.8, 100.5],
                "close": [100.0, 101.0, 104.0],
                "volume": [10.0, 10.0, 10.0],
            },
            index=index,
        )
        row = _simulate_h6_trade(
            symbol="ETHUSDT",
            timestamp=index[0],
            execution_row=execution.iloc[0],
            snapshot={"h6_stop_long": 98.0, "signal_family_long": "h6_bridge_breakout"},
            execution_frame=execution,
            engine=DummyEngine(),
        )

        self.assertIsNotNone(row)
        self.assertEqual("time_exit", row["exit_reason"])
        self.assertGreater(row["realized_R"], 0.0)
        self.assertTrue(row["hit_2R"])

    def test_write_reports_emits_summary_and_csvs(self):
        funnel_rows = [
            {
                "symbol": "BTCUSDT",
                "raw_6h_events": 10,
                "passed_structure": 5,
                "passed_shape": 4,
                "passed_12h_context": 4,
                "passed_1d_context": 3,
                "passed_score": 3,
                "opened_candidates": 2,
            }
        ]
        event_rows = [
            {
                "symbol": "BTCUSDT",
                "timestamp": "2026-01-01 00:00:00",
                "year": 2026,
                "realized_R": 1.25,
                "mfe_R": 2.0,
                "mae_R": -0.2,
                "hit_1R": True,
                "hit_2R": True,
                "hold_hours": 12.0,
                "exit_reason": "time_exit",
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            summary = _write_reports(Path(tmpdir), funnel_rows, event_rows, ["BTCUSDT"])
            self.assertEqual(10, summary["funnel_totals"]["raw_6h_events"])
            self.assertEqual(1, summary["metrics"]["trade_count"])
            self.assertTrue((Path(tmpdir) / "summary.json").exists())
            payload = json.loads((Path(tmpdir) / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(1, payload["metrics"]["trade_count"])


if __name__ == "__main__":
    unittest.main()
