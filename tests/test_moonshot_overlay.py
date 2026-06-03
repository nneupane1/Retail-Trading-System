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
                        "min_score": 0.88,
                        "min_expansion": 1.8,
                        "max_expansion_for_score": 2.5,
                        "min_momentum_rank": 0.85,
                        "min_body_strength": 2.8,
                        "max_body_strength_for_score": 5.0,
                        "min_close_position": 0.88,
                        "max_abs_vwap_distance": 0.008,
                        "allow_shape_override": True,
                        "shape_override_min_expansion": 2.2,
                        "shape_override_min_body_strength": 3.4,
                        "shape_override_min_close_position": 0.90,
                        "selection_bonus": 0.04,
                        "base_risk_fraction": 0.0025,
                        "max_group_risk_fraction": 0.015,
                        "risk_by_expansion": [
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
                        "min_daily_momentum": 0.0,
                        "min_weekly_momentum": -0.03,
                        "allow_daily_override": True,
                        "daily_override_min_strength": 0.72,
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
            "row": pd.Series(
                {
                    "range_expansion_factor": 2.25,
                    "body_strength": 3.1,
                    "close_position": 0.91,
                    "vwap_distance_ratio": 0.004,
                },
                name=timestamp,
            ),
            "score": 0.92,
            "selection_score": 0.92,
            "momentum_rank": 0.91,
            "strategy_type": "core",
            "signal_family": "live_paper",
            "risk_group": "core",
        }

        enriched = overlay.apply_to_candidate(candidate, swing_snapshot={})

        self.assertEqual(enriched["strategy_type"], "intraday_moonshot")
        self.assertGreaterEqual(enriched["selection_score"], 0.85)
        self.assertEqual(enriched["risk_group"], "intraday_moonshot")
        self.assertAlmostEqual(enriched["risk_fraction_override"], 0.0045, places=7)

    def test_intraday_overlay_can_use_shape_override_below_raw_score_floor(self):
        overlay = MoonshotOverlay(config=DummyConfig())
        timestamp = pd.Timestamp("2026-01-01 12:00:00")
        candidate = {
            "symbol": "BTCUSDT",
            "timestamp": timestamp,
            "row": pd.Series(
                {
                    "range_expansion_factor": 2.35,
                    "body_strength": 3.8,
                    "close_position": 0.93,
                    "vwap_distance_ratio": 0.003,
                },
                name=timestamp,
            ),
            "score": 0.87,
            "selection_score": 0.87,
            "momentum_rank": 0.95,
            "strategy_type": "core",
            "signal_family": "live_paper",
            "risk_group": "core",
        }

        enriched = overlay.apply_to_candidate(candidate, swing_snapshot={})

        self.assertEqual(enriched["strategy_type"], "intraday_moonshot")
        self.assertEqual(enriched["risk_group"], "intraday_moonshot")

    def test_intraday_overlay_rejects_late_stretched_vwap_candidate(self):
        overlay = MoonshotOverlay(config=DummyConfig())
        timestamp = pd.Timestamp("2026-01-01 12:00:00")
        candidate = {
            "symbol": "BTCUSDT",
            "timestamp": timestamp,
            "row": pd.Series(
                {
                    "range_expansion_factor": 2.25,
                    "body_strength": 3.1,
                    "close_position": 0.91,
                    "vwap_distance_ratio": 0.015,
                },
                name=timestamp,
            ),
            "score": 0.94,
            "selection_score": 0.94,
            "momentum_rank": 0.95,
            "strategy_type": "core",
            "signal_family": "live_paper",
            "risk_group": "core",
        }

        enriched = overlay.apply_to_candidate(candidate, swing_snapshot={})

        self.assertEqual(enriched["strategy_type"], "core")
        self.assertIsNone(enriched["moonshot_score"])

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

    def test_swing_overlay_can_activate_on_strong_daily_override(self):
        overlay = MoonshotOverlay(config=DummyConfig())
        timestamp = pd.Timestamp("2026-01-01 12:00:00")
        candidate = {
            "symbol": "ETHUSDT",
            "timestamp": timestamp,
            "row": pd.Series(
                {
                    "range_expansion_factor": 1.0,
                    "body_strength": 2.2,
                    "close_position": 0.72,
                    "vwap_distance_ratio": 0.004,
                },
                name=timestamp,
            ),
            "score": 0.86,
            "selection_score": 0.86,
            "momentum_rank": 0.90,
            "strategy_type": "core",
            "signal_family": "live_paper",
            "risk_group": "core",
        }
        swing_snapshot = {
            "daily_breakout_active": True,
            "weekly_breakout_active": False,
            "daily_momentum": 0.04,
            "weekly_momentum": -0.05,
            "daily_range_expansion": 1.3,
            "weekly_range_expansion": 0.9,
            "daily_strength": 0.80,
            "weekly_strength": 0.10,
        }

        enriched = overlay.apply_to_candidate(candidate, swing_snapshot=swing_snapshot)

        self.assertEqual(enriched["strategy_type"], "swing_moonshot")
        self.assertEqual(enriched["risk_group"], "swing_moonshot")
        self.assertGreater(float(enriched["moonshot_score"]), 0.0)


if __name__ == "__main__":
    unittest.main()
