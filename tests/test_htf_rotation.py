import unittest

import pandas as pd

from entry.htf_rotation import (
    HTFRotationEngine,
    build_htf_rotation_snapshots_by_symbol,
)


class DummyConfig:
    def __init__(self):
        self.data = {
            "features": {
                "ema_periods": {"fast": 20, "slow": 50},
            },
            "strategy": {
                "htf_12h_rotation": {
                    "enabled": True,
                    "base_risk_fraction": 0.0025,
                    "max_total_risk_fraction": 0.008,
                    "max_open_positions": 2,
                    "min_history_bars": 5,
                    "top_k": 1,
                    "min_leader_score": 0.70,
                    "min_relative_strength": 0.70,
                    "min_liquidity_percentile": 0.0,
                    "liquidity_lookback": 3,
                    "volume_expansion_lookback": 3,
                    "min_volume_expansion": 1.0,
                    "min_range_expansion": 1.0,
                    "min_positive_periods": 2,
                    "max_vwap_distance": 0.03,
                    "max_ema_distance": 0.08,
                    "strong_body_strength": 1.1,
                    "strong_close_position": 0.60,
                    "supportive_expansion": 1.0,
                    "strong_expansion": 1.3,
                    "trailing_lookback": 2,
                    "atr_stop_buffer": 0.5,
                    "daily_momentum_lookback": 1,
                    "weekly_momentum_lookback": 1,
                    "daily_slope_lookback": 1,
                    "weekly_slope_lookback": 1,
                    "allow_daily_or_weekly_confirmation": True,
                    "decay_12h_candles": 2,
                    "decay_rank_floor": 0.5,
                    "decay_leader_score": 0.5,
                    "rank_entry_floor": 0.0,
                    "require_rank_improvement": False,
                    "selection_bonus": 0.02,
                    "long_risk_multiplier": 1.0,
                    "selection_threshold_offset": -0.04,
                    "selection_min_threshold": 0.70,
                    "selection_max_threshold": 0.95,
                    "allow_pyramiding": False,
                    "max_hold_12h_candles": 144,
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


class HTFRotationTests(unittest.TestCase):
    def _build_frames(self, *, stretched=False, daily_neutral=False):
        index_12h = pd.to_datetime(
            [
                "2026-01-01 00:00:00",
                "2026-01-01 12:00:00",
                "2026-01-02 00:00:00",
                "2026-01-02 12:00:00",
                "2026-01-03 00:00:00",
                "2026-01-03 12:00:00",
            ]
        )
        btc_vwap_distance = [0.005, 0.006, 0.007, 0.009, 0.010, 0.045 if stretched else 0.012]
        btc = pd.DataFrame(
            {
                "open": [100, 102, 104, 106, 109, 113],
                "high": [102, 104, 106, 109, 113, 118],
                "low": [99, 101, 103, 105, 108, 112],
                "close": [101, 103, 105, 108, 112, 117],
                "volume": [1000, 1100, 1200, 1400, 1800, 2600],
                "ema20": [100, 101, 102, 104, 107, 111],
                "ema50": [98, 99, 100, 101, 103, 106],
                "atr": [2.0, 2.0, 2.1, 2.2, 2.4, 2.6],
                "body_strength": [1.0, 1.1, 1.2, 1.4, 1.6, 2.0],
                "close_position": [0.62, 0.65, 0.68, 0.74, 0.82, 0.90],
                "vwap_distance_ratio": btc_vwap_distance,
                "ema_gap_ratio": [0.010, 0.012, 0.014, 0.018, 0.024, 0.030],
                "range_expansion_factor": [1.0, 1.0, 1.05, 1.10, 1.25, 1.55],
            },
            index=index_12h,
        )
        eth = pd.DataFrame(
            {
                "open": [100, 100, 100, 101, 101, 102],
                "high": [101, 101, 101, 102, 102, 103],
                "low": [99, 99, 99, 100, 100, 101],
                "close": [100, 100, 100, 101, 101, 102],
                "volume": [1500, 1500, 1450, 1500, 1520, 1490],
                "ema20": [100, 100, 100, 100.2, 100.4, 100.8],
                "ema50": [99, 99, 99, 99.5, 99.8, 100.1],
                "atr": [1.5, 1.5, 1.5, 1.5, 1.6, 1.6],
                "body_strength": [0.9, 0.9, 0.9, 1.0, 1.0, 1.0],
                "close_position": [0.55, 0.55, 0.55, 0.58, 0.58, 0.60],
                "vwap_distance_ratio": [0.004, 0.004, 0.004, 0.005, 0.005, 0.006],
                "ema_gap_ratio": [0.004, 0.004, 0.004, 0.005, 0.005, 0.006],
                "range_expansion_factor": [0.9, 0.95, 0.95, 1.0, 1.0, 1.02],
            },
            index=index_12h,
        )
        index_1d = pd.to_datetime(
            [
                "2025-12-31 00:00:00",
                "2026-01-01 00:00:00",
                "2026-01-02 00:00:00",
                "2026-01-03 00:00:00",
            ]
        )
        if daily_neutral:
            btc_1d = pd.DataFrame(
                {
                    "high": [103, 106, 112, 113],
                    "low": [98, 101, 107, 107],
                    "close": [101, 105, 111, 110],
                    "ema20": [100, 102, 106, 111],
                    "ema50": [98, 99, 102, 106],
                },
                index=index_1d,
            )
        else:
            btc_1d = pd.DataFrame(
                {
                    "high": [103, 106, 112, 118],
                    "low": [98, 101, 107, 112],
                    "close": [101, 105, 111, 117],
                    "ema20": [100, 102, 106, 111],
                    "ema50": [98, 99, 102, 106],
                },
                index=index_1d,
            )
        eth_1d = pd.DataFrame(
            {
                "high": [101, 101, 102, 103],
                "low": [99, 99, 100, 101],
                "close": [100, 100, 101, 102],
                "ema20": [99.8, 99.9, 100.1, 100.5],
                "ema50": [99.3, 99.4, 99.6, 99.8],
            },
            index=index_1d,
        )
        index_1w = pd.to_datetime(["2025-12-28 00:00:00", "2026-01-04 00:00:00"])
        btc_1w = pd.DataFrame(
            {
                "high": [108, 120],
                "low": [94, 109],
                "close": [102, 118],
                "ema20": [99, 108],
                "ema50": [96, 102],
            },
            index=index_1w,
        )
        eth_1w = pd.DataFrame(
            {
                "high": [102, 104],
                "low": [98, 100],
                "close": [100, 103],
                "ema20": [99.5, 100.8],
                "ema50": [99.0, 99.8],
            },
            index=index_1w,
        )
        execution_index = pd.to_datetime(
            [
                "2026-01-03 11:45:00",
                "2026-01-03 12:00:00",
                "2026-01-03 12:15:00",
            ]
        )
        return (
            {"BTCUSDT": execution_index, "ETHUSDT": execution_index},
            {"BTCUSDT": btc, "ETHUSDT": eth},
            {"BTCUSDT": btc_1d, "ETHUSDT": eth_1d},
            {"BTCUSDT": btc_1w, "ETHUSDT": eth_1w},
        )

    def test_rotation_selects_leading_symbol_on_new_12h_candle(self):
        config = DummyConfig()
        execution_indexes, frames_12h, frames_1d, frames_1w = self._build_frames()

        snapshots = build_htf_rotation_snapshots_by_symbol(
            execution_indexes,
            frames_12h,
            frames_1d,
            frames_1w,
            config=config,
        )

        timestamp = execution_indexes["BTCUSDT"][1]
        self.assertTrue(bool(snapshots["BTCUSDT"].loc[timestamp, "signal_event_long"]))
        self.assertFalse(bool(snapshots["ETHUSDT"].loc[timestamp, "signal_event_long"]))
        self.assertIn(
            snapshots["BTCUSDT"].loc[timestamp, "signal_family_long"],
            {"leader_acceleration", "leader_persistence"},
        )

    def test_rotation_rejects_overstretched_leader(self):
        config = DummyConfig()
        execution_indexes, frames_12h, frames_1d, frames_1w = self._build_frames(
            stretched=True
        )

        snapshots = build_htf_rotation_snapshots_by_symbol(
            execution_indexes,
            frames_12h,
            frames_1d,
            frames_1w,
            config=config,
        )

        timestamp = execution_indexes["BTCUSDT"][1]
        self.assertFalse(bool(snapshots["BTCUSDT"].loc[timestamp, "signal_event_long"]))
        self.assertFalse(bool(snapshots["BTCUSDT"].loc[timestamp, "htf_pass_stretch_long"]))

    def test_rotation_engine_builds_candidate_with_htf_execution_profile(self):
        config = DummyConfig()
        execution_indexes, frames_12h, frames_1d, frames_1w = self._build_frames()
        snapshots = build_htf_rotation_snapshots_by_symbol(
            execution_indexes,
            frames_12h,
            frames_1d,
            frames_1w,
            config=config,
        )
        engine = HTFRotationEngine(config=config)
        timestamp = execution_indexes["BTCUSDT"][1]
        execution_row = pd.Series(
            {"close": 117.0, "low": 116.5, "high": 118.0},
            name=timestamp,
        )

        candidate = engine.build_candidate(
            symbol="BTCUSDT",
            timestamp=timestamp,
            execution_row=execution_row,
            snapshot=snapshots["BTCUSDT"].loc[timestamp].to_dict(),
            momentum_rank=0.95,
            top_symbols=["BTCUSDT"],
        )

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["strategy_type"], "htf_12h_rotation")
        self.assertEqual(candidate["risk_group"], "htf_12h_rotation")
        self.assertFalse(candidate["apply_score_bucket_filters"])
        self.assertLess(candidate["stop_price_override"], execution_row["close"])
        self.assertIn(
            candidate["htf_signal_family"],
            {"leader_acceleration", "leader_persistence"},
        )

    def test_rotation_allows_weekly_context_to_rescue_neutral_daily_state(self):
        config = DummyConfig()
        execution_indexes, frames_12h, frames_1d, frames_1w = self._build_frames(
            daily_neutral=True
        )

        snapshots = build_htf_rotation_snapshots_by_symbol(
            execution_indexes,
            frames_12h,
            frames_1d,
            frames_1w,
            config=config,
        )

        timestamp = execution_indexes["BTCUSDT"][1]
        row = snapshots["BTCUSDT"].loc[timestamp]
        self.assertFalse(bool(row["htf_pass_1d_context_long"]))
        self.assertTrue(bool(row["htf_pass_1w_context_long"]))
        self.assertTrue(bool(row["htf_pass_context_gate_long"]))
        self.assertTrue(bool(row["signal_event_long"]))


if __name__ == "__main__":
    unittest.main()
