import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from common.daily_leader_focus import (
    build_daily_leader_schedule,
    build_daily_leader_summary,
    write_daily_leader_focus_reports,
)


class DailyLeaderFocusTests(unittest.TestCase):
    def test_schedule_uses_prior_day_leader_without_lookahead(self):
        dates = pd.date_range("2026-01-01", periods=5, freq="D")
        btc = pd.DataFrame(
            {
                "close": [100, 110, 108, 112, 114],
                "volume": [1000, 1000, 1000, 1000, 1000],
            },
            index=dates,
        )
        eth = pd.DataFrame(
            {
                "close": [100, 101, 120, 121, 122],
                "volume": [1000, 1000, 1000, 1000, 1000],
            },
            index=dates,
        )

        schedule, candidates = build_daily_leader_schedule(
            {"BTCUSDT": btc, "ETHUSDT": eth},
            top_n=1,
            lookback_days=1,
            min_history_days=1,
        )

        self.assertFalse(candidates.empty)
        day3 = schedule.loc[schedule["trade_date"] == pd.Timestamp("2026-01-03")]
        self.assertEqual(["BTCUSDT"], day3["symbol"].tolist())
        day4 = schedule.loc[schedule["trade_date"] == pd.Timestamp("2026-01-04")]
        self.assertEqual(["ETHUSDT"], day4["symbol"].tolist())

    def test_schedule_respects_positive_return_and_liquidity_filter(self):
        dates = pd.date_range("2026-01-01", periods=4, freq="D")
        strong = pd.DataFrame(
            {
                "close": [100, 105, 106, 104],
                "quote_volume": [10_000_000, 10_000_000, 10_000_000, 10_000_000],
            },
            index=dates,
        )
        weak = pd.DataFrame(
            {
                "close": [100, 130, 120, 119],
                "quote_volume": [100_000, 100_000, 100_000, 100_000],
            },
            index=dates,
        )

        schedule, _ = build_daily_leader_schedule(
            {"STRONGUSDT": strong, "WEAKUSDT": weak},
            top_n=1,
            lookback_days=1,
            min_history_days=1,
            min_daily_quote_volume=1_000_000,
            require_positive_return=True,
        )

        self.assertTrue((schedule["symbol"] == "STRONGUSDT").all())

    def test_reports_are_written(self):
        dates = pd.date_range("2026-01-01", periods=3, freq="D")
        frame = pd.DataFrame(
            {
                "close": [100, 102, 101],
                "volume": [1000, 1000, 1000],
            },
            index=dates,
        )
        schedule, candidates = build_daily_leader_schedule(
            {"BTCUSDT": frame},
            top_n=1,
            lookback_days=1,
            min_history_days=1,
        )
        summary = build_daily_leader_summary(
            schedule=schedule,
            candidates=candidates,
            top_n=1,
            lookback_days=1,
            source_symbols=["BTCUSDT"],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts = write_daily_leader_focus_reports(
                Path(tmpdir),
                schedule=schedule,
                candidates=candidates,
                summary=summary,
            )
            self.assertTrue(Path(artifacts["leader_schedule_csv"]).exists())
            self.assertTrue(Path(artifacts["leader_candidates_csv"]).exists())
            payload = json.loads(Path(artifacts["summary_json"]).read_text(encoding="utf-8"))
            self.assertEqual("research_scaffold_only", payload["mode"])


if __name__ == "__main__":
    unittest.main()
