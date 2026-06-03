import unittest

import pandas as pd

from entry.htf_moonshot import HTFMoonshotEngine, build_htf_12h_snapshots


class DummyConfig:
    def __init__(self):
        self.data = {
            "features": {
                "ema_periods": {"fast": 20, "slow": 50},
            },
            "strategy": {
                "htf_12h_moonshot": {
                    "enabled": True,
                    "base_risk_fraction": 0.0035,
                    "max_total_risk_fraction": 0.012,
                    "max_open_positions": 2,
                    "min_score": 7,
                    "breakout_lookback": 3,
                    "daily_breakout_lookback": 3,
                    "weekly_breakout_lookback": 2,
                    "compression_lookback": 3,
                    "trailing_lookback": 2,
                    "atr_stop_buffer": 0.5,
                    "max_vwap_distance": 0.03,
                    "max_ema_distance": 0.08,
                    "daily_momentum_lookback": 1,
                    "weekly_momentum_lookback": 1,
                    "daily_slope_lookback": 1,
                    "weekly_slope_lookback": 1,
                    "max_hold_12h_candles": 120,
                    "selection_bonus": 0.08,
                    "top_mover_bonus": 0.03,
                    "long_risk_multiplier": 1.0,
                    "short_risk_multiplier": 0.6,
                    "allow_pyramiding": False,
                }
            },
        }

    def get(self, *keys, default=None):
        value = self.data
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value

    def require(self, *keys):
        value = self.data
        for key in keys:
            value = value[key]
        return value


class HTFMoonshotTests(unittest.TestCase):
    def _build_frames(self):
        df_12h = pd.DataFrame(
            {
                "high": [100, 102, 103, 109],
                "low": [95, 97, 98, 101],
                "close": [99, 101, 102, 108],
                "ema20": [98, 99, 100, 103],
                "ema50": [96, 97, 98, 100],
                "atr": [2.0, 2.0, 2.1, 2.4],
                "body_strength": [1.0, 1.2, 1.3, 2.2],
                "close_position": [0.60, 0.62, 0.65, 0.88],
                "vwap_distance_ratio": [0.010, 0.012, 0.013, 0.018],
                "ema_gap_ratio": [0.010, 0.012, 0.013, 0.020],
            },
            index=pd.to_datetime(
                [
                    "2026-01-01 00:00:00",
                    "2026-01-01 12:00:00",
                    "2026-01-02 00:00:00",
                    "2026-01-02 12:00:00",
                ]
            ),
        )
        df_1d = pd.DataFrame(
            {
                "high": [100, 102, 110],
                "low": [95, 97, 101],
                "close": [99, 101, 109],
                "ema20": [98, 99, 103],
                "ema50": [96, 97, 100],
            },
            index=pd.to_datetime(
                ["2025-12-31 00:00:00", "2026-01-01 00:00:00", "2026-01-02 00:00:00"]
            ),
        )
        df_1w = pd.DataFrame(
            {
                "high": [100, 112],
                "low": [90, 99],
                "close": [98, 110],
                "ema20": [95, 100],
                "ema50": [92, 96],
            },
            index=pd.to_datetime(["2025-12-28 00:00:00", "2026-01-04 00:00:00"]),
        )
        execution_index = pd.to_datetime(
            [
                "2026-01-02 11:45:00",
                "2026-01-02 12:00:00",
                "2026-01-02 12:15:00",
            ]
        )
        return execution_index, df_12h, df_1d, df_1w

    def test_htf_signal_only_triggers_on_closed_12h_candle(self):
        config = DummyConfig()
        execution_index, df_12h, df_1d, df_1w = self._build_frames()

        snapshots = build_htf_12h_snapshots(execution_index, df_12h, df_1d, df_1w, config=config)

        self.assertFalse(bool(snapshots.loc[execution_index[0], "signal_event_long"]))
        self.assertTrue(bool(snapshots.loc[execution_index[1], "signal_event_long"]))
        self.assertFalse(bool(snapshots.loc[execution_index[2], "signal_event_long"]))

    def test_htf_engine_builds_isolated_candidate_with_structural_stop(self):
        config = DummyConfig()
        execution_index, df_12h, df_1d, df_1w = self._build_frames()
        snapshots = build_htf_12h_snapshots(execution_index, df_12h, df_1d, df_1w, config=config)
        engine = HTFMoonshotEngine(config=config)
        execution_row = pd.Series(
            {
                "close": 108.0,
                "low": 107.5,
                "high": 108.2,
            },
            name=execution_index[1],
        )

        candidate = engine.build_candidate(
            symbol="BTCUSDT",
            timestamp=execution_index[1],
            execution_row=execution_row,
            snapshot=snapshots.loc[execution_index[1]].to_dict(),
            momentum_rank=0.95,
            top_symbols=["BTCUSDT"],
        )

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["strategy_type"], "htf_12h_moonshot")
        self.assertEqual(candidate["risk_group"], "htf_12h_moonshot")
        self.assertFalse(candidate["apply_score_bucket_filters"])
        self.assertLess(candidate["stop_price_override"], execution_row["close"])
        self.assertIn(candidate["htf_signal_family"], {"structure_breakout", "trend_pullback"})

    def test_htf_short_candidate_uses_reduced_short_risk(self):
        config = DummyConfig()
        engine = HTFMoonshotEngine(config=config)
        execution_row = pd.Series(
            {
                "close": 100.0,
                "low": 99.4,
                "high": 100.6,
            },
            name=pd.Timestamp("2026-01-02 12:00:00"),
        )
        snapshot = {
            "htf_12h_new_candle": True,
            "signal_event_long": False,
            "signal_event_short": True,
            "signal_family_short": "structure_breakout",
            "htf_score_short": 8.0,
            "htf_stop_short": 103.0,
            "htf_vwap_distance_ratio_12h": 0.01,
            "htf_body_strength_12h": 2.0,
            "htf_close_position_12h": 0.15,
            "htf_context_1d": "bearish",
            "htf_context_1w": "bearish",
            "htf_entry_reason_short": "12h structure breakout",
            "htf_stop_reason_short": "12h structural high with ATR buffer",
            "htf_trailing_state_short": "confirmation",
            "htf_range_expansion_12h": 1.4,
        }

        candidate = engine.build_candidate(
            symbol="BTCUSDT",
            timestamp=execution_row.name,
            execution_row=execution_row,
            snapshot=snapshot,
            momentum_rank=0.90,
            top_symbols=["BTCUSDT"],
        )

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["side"], "short")
        self.assertAlmostEqual(candidate["risk_fraction_override"], 0.0035 * 0.6, places=7)


if __name__ == "__main__":
    unittest.main()
