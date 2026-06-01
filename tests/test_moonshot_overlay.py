import tempfile
import unittest

import pandas as pd

from entry.moonshot import MoonshotOverlay, build_swing_snapshots


class DummyConfig:
    def __init__(self):
        self.data = {
            "strategy": {
                "moonshots": {
                    "enabled": True,
                    "intraday": {
                        "enabled": True,
                        "min_score": 0.85,
                        "min_expansion": 1.4,
                        "max_expansion_for_score": 2.5,
                        "min_momentum_rank": 0.75,
                        "selection_bonus": 0.06,
                        "base_risk_fraction": 0.0025,
                        "max_group_risk_fraction": 0.015,
                        "risk_by_expansion": [
                            {"min_expansion": 1.4, "risk_fraction": 0.0025},
                            {"min_expansion": 1.8, "risk_fraction": 0.0035},
                            {"min_expansion": 2.2, "risk_fraction": 0.0045},
                        ],
                    },
                    "swing": {
                        "enabled": True,
                        "min_score": 0.82,
                        "min_rank": 0.75,
                        "daily_breakout_lookback": 3,
                        "weekly_breakout_lookback": 2,
                        "daily_momentum_lookback": 1,
                        "weekly_momentum_lookback": 1,
                        "daily_expansion_lookback": 3,
                        "weekly_expansion_lookback": 2,
                        "daily_expansion_threshold": 1.05,
                        "weekly_expansion_threshold": 1.0,
                        "selection_bonus": 0.10,
                        "risk_fraction": 0.0015,
                        "max_group_risk_fraction": 0.01,
                    },
                }
            }
        }

    def get(self, *keys, default=None):
        value = self.data
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value


class MoonshotOverlayTests(unittest.TestCase):
    def test_intraday_overlay_marks_high_expansion_candidate(self):
        overlay = MoonshotOverlay(config=DummyConfig())
        timestamp = pd.Timestamp("2026-01-01 12:00:00")
        candidate = {
            "symbol": "BTCUSDT",
            "timestamp": timestamp,
            "row": pd.Series({"range_expansion_factor": 2.25}, name=timestamp),
            "score": 0.88,
            "selection_score": 0.88,
            "momentum_rank": 0.91,
            "strategy_type": "core",
            "signal_family": "live_paper",
            "risk_group": "core",
        }

        enriched = overlay.apply_to_candidate(candidate, swing_snapshot={})

        self.assertEqual(enriched["strategy_type"], "intraday_moonshot")
        self.assertGreater(enriched["selection_score"], candidate["selection_score"])
        self.assertEqual(enriched["risk_group"], "intraday_moonshot")
        self.assertAlmostEqual(enriched["risk_fraction_override"], 0.0045, places=7)

    def test_swing_snapshots_activate_on_breakout_and_positive_momentum(self):
        config = DummyConfig()
        execution_index = pd.date_range("2026-01-01", periods=5, freq="15min")
        daily_index = pd.date_range("2025-12-28", periods=8, freq="1D")
        weekly_index = pd.date_range("2025-11-30", periods=5, freq="1W")
        df_1d = pd.DataFrame(
            {
                "high": [10, 11, 12, 13, 14, 15, 16, 20],
                "low": [9, 10, 11, 12, 13, 14, 15, 17],
                "close": [9.5, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5, 19.5],
            },
            index=daily_index,
        )
        df_1w = pd.DataFrame(
            {
                "high": [10, 11, 12, 13, 18],
                "low": [9, 10, 11, 12, 15],
                "close": [9.5, 10.5, 11.5, 12.5, 17.5],
            },
            index=weekly_index,
        )

        snapshots = build_swing_snapshots(execution_index, df_1d, df_1w, config=config)
        latest = snapshots.iloc[-1]

        self.assertTrue(bool(latest["swing_active"]))
        self.assertGreater(float(latest["swing_strength"]), 0.0)
        self.assertTrue(bool(latest["daily_breakout_active"]))


if __name__ == "__main__":
    unittest.main()
