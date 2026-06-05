import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backtest.validate_h1_execution import _simulate_h1_trade, _write_reports


class DummyEngine:
    max_hold_1h_candles = 2


class ValidateH1ExecutionTests(unittest.TestCase):
    def test_simulate_h1_long_trade_stops_out_on_first_stop_touch(self):
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
        row = _simulate_h1_trade(
            symbol="BTCUSDT",
            side="long",
            timestamp=index[0],
            execution_row=execution.iloc[0],
            snapshot={"h1_stop_long": 98.0, "signal_family_long": "h1_structure_continuation"},
            execution_frame=execution,
            engine=DummyEngine(),
        )

        self.assertIsNotNone(row)
        self.assertEqual("stop", row["exit_reason"])
        self.assertEqual(-1.0, row["realized_R"])

    def test_simulate_h1_short_trade_time_exits_when_stop_not_hit(self):
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
                "high": [100.5, 100.2, 99.5],
                "low": [99.5, 98.4, 97.5],
                "close": [100.0, 98.8, 98.0],
                "volume": [10.0, 10.0, 10.0],
            },
            index=index,
        )
        row = _simulate_h1_trade(
            symbol="ETHUSDT",
            side="short",
            timestamp=index[0],
            execution_row=execution.iloc[0],
            snapshot={"h1_stop_short": 102.0, "signal_family_short": "h1_structure_continuation"},
            execution_frame=execution,
            engine=DummyEngine(),
        )

        self.assertIsNotNone(row)
        self.assertEqual("time_exit", row["exit_reason"])
        self.assertGreater(row["realized_R"], 0.0)
        self.assertTrue(row["hit_1R"])

    def test_write_reports_emits_summary_and_csvs(self):
        funnel_rows = [
            {
                "symbol": "BTCUSDT",
                "raw_1h_events": 12,
                "passed_structure_long": 5,
                "passed_structure_short": 4,
                "passed_shape_long": 4,
                "passed_shape_short": 3,
                "passed_6h_context_long": 4,
                "passed_6h_context_short": 3,
                "passed_12h_context_long": 4,
                "passed_12h_context_short": 3,
                "passed_score_long": 3,
                "passed_score_short": 2,
                "opened_long_candidates": 2,
                "opened_short_candidates": 1,
            }
        ]
        event_rows = [
            {
                "symbol": "BTCUSDT",
                "timestamp": "2026-01-01 00:00:00",
                "year": 2026,
                "side": "long",
                "realized_R": 1.25,
                "mfe_R": 2.0,
                "mae_R": -0.2,
                "hit_1R": True,
                "hit_2R": True,
                "hold_hours": 4.0,
                "exit_reason": "time_exit",
            },
            {
                "symbol": "BTCUSDT",
                "timestamp": "2026-01-01 02:00:00",
                "year": 2026,
                "side": "short",
                "realized_R": -1.0,
                "mfe_R": 0.5,
                "mae_R": -1.0,
                "hit_1R": False,
                "hit_2R": False,
                "hold_hours": 2.0,
                "exit_reason": "stop",
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            summary = _write_reports(Path(tmpdir), funnel_rows, event_rows, ["BTCUSDT"])
            self.assertEqual(12, summary["funnel_totals"]["raw_1h_events"])
            self.assertEqual(2, summary["metrics"]["trade_count"])
            self.assertEqual({"long": 1, "short": 1}, summary["metrics"]["long_short_split"])
            self.assertTrue((Path(tmpdir) / "summary.json").exists())
            payload = json.loads((Path(tmpdir) / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(2, payload["metrics"]["trade_count"])


if __name__ == "__main__":
    unittest.main()
