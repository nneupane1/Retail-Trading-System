import unittest

import pandas as pd

from entry.h1_execution import H1ExecutionEngine, build_h1_execution_snapshots
from entry.h6_moonshot import H6MoonshotEngine, H6StandardEngine, build_h6_moonshot_snapshots


class DummyConfig:
    def __init__(self):
        self.data = {
            "strategy": {
                "h1_execution": {
                    "enabled": True,
                    "breakout_lookback": 3,
                    "body_strength_min": 1.2,
                    "close_position_min": 0.7,
                    "expansion_min": 1.0,
                    "max_abs_vwap_distance": 0.03,
                    "context_6h_momentum_min": 0.0,
                    "context_12h_momentum_min": -0.02,
                    "min_score": 0.70,
                    "require_6h_context": True,
                    "allow_12h_context_override": True,
                    "trailing_lookback": 2,
                    "atr_stop_buffer": 0.5,
                    "base_risk_fraction": 0.002,
                    "max_total_risk_fraction": 0.006,
                    "max_open_positions": 2,
                    "max_hold_1h_candles": 24,
                },
                "h6_moonshot": {
                    "enabled": True,
                    "breakout_lookback": 3,
                    "body_strength_min": 1.3,
                    "close_position_min": 0.72,
                    "expansion_min": 1.0,
                    "max_abs_vwap_distance": 0.03,
                    "min_score": 0.72,
                    "atr_stop_buffer": 0.5,
                    "trailing_lookback": 2,
                    "context_12h_momentum_min": 0.0,
                    "context_1d_momentum_min": -0.02,
                    "base_risk_fraction": 0.0025,
                    "max_total_risk_fraction": 0.008,
                    "max_open_positions": 2,
                    "max_hold_6h_candles": 30,
                },
                "h6_standard": {
                    "enabled": True,
                    "base_risk_fraction": 0.0018,
                    "max_total_risk_fraction": 0.0055,
                    "max_open_positions": 2,
                    "max_hold_6h_candles": 18,
                    "min_score": 0.68,
                    "selection_bonus": 0.02,
                    "top_mover_bonus": 0.02,
                },
            }
        }

    def get(self, *keys, default=None):
        value = self.data
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value


class FutureTimeframeLayerTests(unittest.TestCase):
    def test_h1_scaffold_only_triggers_on_new_1h_candle(self):
        config = DummyConfig()
        index_1h = pd.to_datetime(
            ["2026-01-01 00:00:00", "2026-01-01 01:00:00", "2026-01-01 02:00:00", "2026-01-01 03:00:00"]
        )
        df_1h = pd.DataFrame(
            {
                "high": [100, 101, 102, 106],
                "low": [99, 100, 101, 103],
                "close": [99.5, 100.5, 101.5, 105.5],
                "atr": [1.0, 1.0, 1.1, 1.2],
                "body_strength": [1.0, 1.0, 1.1, 1.8],
                "close_position": [0.55, 0.60, 0.65, 0.88],
                "vwap_distance_ratio": [0.01, 0.012, 0.014, 0.015],
                "ema_gap_ratio": [0.01, 0.011, 0.012, 0.016],
                "range_expansion_factor": [0.9, 0.95, 1.0, 1.2],
            },
            index=index_1h,
        )
        df_6h = pd.DataFrame(
            {"close": [100, 110], "ema20": [99, 104], "ema50": [97, 100]},
            index=pd.to_datetime(["2026-01-01 00:00:00", "2026-01-01 06:00:00"]),
        )
        df_12h = pd.DataFrame(
            {"close": [98, 111], "ema20": [97, 103], "ema50": [95, 100]},
            index=pd.to_datetime(["2026-01-01 00:00:00", "2026-01-01 12:00:00"]),
        )
        execution_index = pd.to_datetime(
            ["2026-01-01 02:45:00", "2026-01-01 03:00:00", "2026-01-01 03:15:00"]
        )

        snapshots = build_h1_execution_snapshots(
            execution_index,
            df_1h,
            df_6h,
            df_12h,
            config=config,
        )

        self.assertFalse(bool(snapshots.loc[execution_index[0], "signal_event_long"]))
        self.assertTrue(bool(snapshots.loc[execution_index[1], "h1_new_candle"]))
        self.assertTrue(bool(snapshots.loc[execution_index[1], "signal_event_long"]))
        self.assertFalse(bool(snapshots.loc[execution_index[2], "signal_event_long"]))

    def test_h1_engine_builds_dormant_candidate_shape(self):
        config = DummyConfig()
        engine = H1ExecutionEngine(config=config)
        execution_row = pd.Series({"close": 105.5}, name=pd.Timestamp("2026-01-01 03:00:00"))
        snapshot = {
            "h1_new_candle": True,
            "signal_event_long": True,
            "h1_score_long": 0.84,
            "h1_stop_long": 102.0,
            "h1_body_strength": 1.8,
            "h1_range_expansion": 1.2,
            "h1_context_6h": "bullish",
            "signal_family_long": "h1_structure_continuation",
        }

        candidate = engine.build_candidate(
            symbol="BTCUSDT",
            timestamp=execution_row.name,
            execution_row=execution_row,
            snapshot=snapshot,
            momentum_rank=0.8,
            top_symbols=[],
        )

        self.assertIsNotNone(candidate)
        self.assertEqual("h1_execution", candidate["strategy_type"])
        self.assertTrue(candidate["deferred_layer"])

    def test_h1_engine_uses_side_specific_threshold_and_risk_controls(self):
        config = DummyConfig()
        config.data["strategy"]["h1_execution"]["long_selection_threshold_offset"] = 0.01
        config.data["strategy"]["h1_execution"]["short_selection_threshold_offset"] = -0.04
        config.data["strategy"]["h1_execution"]["long_risk_multiplier"] = 0.85
        config.data["strategy"]["h1_execution"]["short_risk_multiplier"] = 1.10
        engine = H1ExecutionEngine(config=config)
        execution_row = pd.Series({"close": 105.5}, name=pd.Timestamp("2026-01-01 03:00:00"))

        long_candidate = engine.build_candidate(
            symbol="BTCUSDT",
            timestamp=execution_row.name,
            execution_row=execution_row,
            snapshot={
                "h1_new_candle": True,
                "signal_event_long": True,
                "signal_event_short": False,
                "h1_score_long": 0.84,
                "h1_stop_long": 102.0,
                "h1_body_strength": 1.8,
                "h1_range_expansion": 1.2,
                "h1_context_6h": "bullish",
                "signal_family_long": "h1_structure_continuation",
            },
            momentum_rank=0.8,
            top_symbols=[],
        )
        short_candidate = engine.build_candidate(
            symbol="BTCUSDT",
            timestamp=execution_row.name,
            execution_row=pd.Series({"close": 101.0}, name=execution_row.name),
            snapshot={
                "h1_new_candle": True,
                "signal_event_long": False,
                "signal_event_short": True,
                "h1_score_short": 0.84,
                "h1_stop_short": 103.0,
                "h1_body_strength": 1.8,
                "h1_range_expansion": 1.2,
                "h1_context_6h": "bearish",
                "signal_family_short": "h1_structure_continuation",
            },
            momentum_rank=0.8,
            top_symbols=[],
        )

        self.assertEqual(0.01, long_candidate["selection_threshold_offset"])
        self.assertAlmostEqual(0.002 * 0.85, long_candidate["risk_fraction_override"])
        self.assertEqual(-0.04, short_candidate["selection_threshold_offset"])
        self.assertAlmostEqual(0.002 * 1.10, short_candidate["risk_fraction_override"])

    def test_h1_engine_applies_context_aware_side_policy(self):
        config = DummyConfig()
        config.data["strategy"]["h1_execution"]["context_side_policy"] = {
            "bearish": {
                "allowed_sides": ["short"],
                "short_selection_threshold_offset": -0.05,
                "short_risk_multiplier": 1.15,
            },
            "bullish": {
                "allowed_sides": ["long", "short"],
                "long_selection_threshold_offset": -0.03,
                "short_selection_threshold_offset": 0.02,
                "long_risk_multiplier": 1.05,
                "short_risk_multiplier": 0.90,
            },
        }
        engine = H1ExecutionEngine(config=config)
        execution_row = pd.Series({"close": 105.5}, name=pd.Timestamp("2026-01-01 03:00:00"))

        bearish_long = engine.build_candidate(
            symbol="BTCUSDT",
            timestamp=execution_row.name,
            execution_row=execution_row,
            snapshot={
                "h1_new_candle": True,
                "signal_event_long": True,
                "signal_event_short": False,
                "h1_score_long": 0.84,
                "h1_stop_long": 102.0,
                "h1_body_strength": 1.8,
                "h1_range_expansion": 1.2,
                "h1_context_12h": "bearish",
                "signal_family_long": "h1_structure_continuation",
            },
            momentum_rank=0.8,
            top_symbols=[],
        )
        bearish_short = engine.build_candidate(
            symbol="BTCUSDT",
            timestamp=execution_row.name,
            execution_row=pd.Series({"close": 101.0}, name=execution_row.name),
            snapshot={
                "h1_new_candle": True,
                "signal_event_long": False,
                "signal_event_short": True,
                "h1_score_short": 0.84,
                "h1_stop_short": 103.0,
                "h1_body_strength": 1.8,
                "h1_range_expansion": 1.2,
                "h1_context_12h": "bearish",
                "signal_family_short": "h1_structure_continuation",
            },
            momentum_rank=0.8,
            top_symbols=[],
        )
        bullish_long = engine.build_candidate(
            symbol="BTCUSDT",
            timestamp=execution_row.name,
            execution_row=execution_row,
            snapshot={
                "h1_new_candle": True,
                "signal_event_long": True,
                "signal_event_short": False,
                "h1_score_long": 0.84,
                "h1_stop_long": 102.0,
                "h1_body_strength": 1.8,
                "h1_range_expansion": 1.2,
                "h1_context_12h": "bullish",
                "signal_family_long": "h1_structure_continuation",
            },
            momentum_rank=0.8,
            top_symbols=[],
        )

        self.assertIsNone(bearish_long)
        self.assertIsNotNone(bearish_short)
        self.assertEqual(-0.05, bearish_short["selection_threshold_offset"])
        self.assertAlmostEqual(0.002 * 1.15, bearish_short["risk_fraction_override"])
        self.assertIsNotNone(bullish_long)
        self.assertEqual(-0.03, bullish_long["selection_threshold_offset"])
        self.assertAlmostEqual(0.002 * 1.05, bullish_long["risk_fraction_override"])

    def test_h1_engine_can_allow_elite_long_exception_under_short_only_policy(self):
        config = DummyConfig()
        config.data["strategy"]["h1_execution"]["allowed_sides"] = ["short"]
        config.data["strategy"]["h1_execution"]["elite_long_exception"] = {
            "enabled": True,
            "min_score": 0.90,
            "min_range_expansion": 1.15,
            "min_body_strength": 1.8,
            "min_close_position": 0.82,
            "require_6h_context": True,
            "require_12h_context": True,
            "require_bullish_6h_label": True,
            "require_bullish_12h_label": True,
            "selection_threshold_offset": -0.01,
            "risk_multiplier": 0.80,
        }
        engine = H1ExecutionEngine(config=config)
        execution_row = pd.Series({"close": 105.5}, name=pd.Timestamp("2026-01-01 03:00:00"))

        elite_candidate = engine.build_candidate(
            symbol="BTCUSDT",
            timestamp=execution_row.name,
            execution_row=execution_row,
            snapshot={
                "h1_new_candle": True,
                "signal_event_long": True,
                "signal_event_short": False,
                "h1_score_long": 0.93,
                "h1_stop_long": 102.0,
                "h1_body_strength": 1.9,
                "h1_close_position": 0.88,
                "h1_range_expansion": 1.2,
                "h1_pass_6h_context_long": True,
                "h1_pass_12h_context_long": True,
                "h1_context_6h": "bullish",
                "h1_context_12h": "bullish",
                "signal_family_long": "h1_structure_continuation",
            },
            momentum_rank=0.9,
            top_symbols=[],
        )
        weak_candidate = engine.build_candidate(
            symbol="BTCUSDT",
            timestamp=execution_row.name,
            execution_row=execution_row,
            snapshot={
                "h1_new_candle": True,
                "signal_event_long": True,
                "signal_event_short": False,
                "h1_score_long": 0.86,
                "h1_stop_long": 102.0,
                "h1_body_strength": 1.6,
                "h1_close_position": 0.78,
                "h1_range_expansion": 1.05,
                "h1_pass_6h_context_long": True,
                "h1_pass_12h_context_long": True,
                "h1_context_6h": "bullish",
                "h1_context_12h": "bullish",
                "signal_family_long": "h1_structure_continuation",
            },
            momentum_rank=0.9,
            top_symbols=[],
        )

        self.assertIsNotNone(elite_candidate)
        self.assertTrue(elite_candidate["elite_long_exception_applied"])
        self.assertEqual(-0.01, elite_candidate["selection_threshold_offset"])
        self.assertAlmostEqual(0.002 * 0.80, elite_candidate["risk_fraction_override"])
        self.assertIsNone(weak_candidate)

    def test_h1_engine_can_fallback_from_bearish_boost_to_short_only_policy(self):
        config = DummyConfig()
        config.data["strategy"]["h1_execution"]["allowed_sides"] = ["short"]
        config.data["strategy"]["h1_execution"]["short_selection_threshold_offset"] = -0.02
        config.data["strategy"]["h1_execution"]["short_risk_multiplier"] = 1.0
        config.data["strategy"]["h1_execution"]["context_side_policy"] = {
            "bearish": {
                "allowed_sides": ["short"],
                "short_selection_threshold_offset": -0.05,
                "short_risk_multiplier": 1.15,
            }
        }
        engine = H1ExecutionEngine(config=config)
        execution_row = pd.Series({"close": 101.0}, name=pd.Timestamp("2026-01-01 03:00:00"))

        boosted = engine.build_candidate(
            symbol="BTCUSDT",
            timestamp=execution_row.name,
            execution_row=execution_row,
            snapshot={
                "h1_new_candle": True,
                "signal_event_long": False,
                "signal_event_short": True,
                "h1_score_short": 0.84,
                "h1_stop_short": 103.0,
                "h1_body_strength": 1.8,
                "h1_range_expansion": 1.2,
                "h1_context_12h": "bearish",
                "signal_family_short": "h1_structure_continuation",
            },
            momentum_rank=0.8,
            top_symbols=[],
            runtime_policy_state={"fallback_to_short_only": False, "label": "boost_active"},
        )
        fallback = engine.build_candidate(
            symbol="BTCUSDT",
            timestamp=execution_row.name,
            execution_row=execution_row,
            snapshot={
                "h1_new_candle": True,
                "signal_event_long": False,
                "signal_event_short": True,
                "h1_score_short": 0.84,
                "h1_stop_short": 103.0,
                "h1_body_strength": 1.8,
                "h1_range_expansion": 1.2,
                "h1_context_12h": "bearish",
                "signal_family_short": "h1_structure_continuation",
            },
            momentum_rank=0.8,
            top_symbols=[],
            runtime_policy_state={"fallback_to_short_only": True, "label": "fallback_short_only"},
        )

        self.assertEqual(-0.05, boosted["selection_threshold_offset"])
        self.assertAlmostEqual(0.002 * 1.15, boosted["risk_fraction_override"])
        self.assertFalse(boosted["context_policy_fallback_active"])
        self.assertEqual(-0.02, fallback["selection_threshold_offset"])
        self.assertAlmostEqual(0.002 * 1.0, fallback["risk_fraction_override"])
        self.assertTrue(fallback["context_policy_fallback_active"])

    def test_h6_scaffold_builds_event_on_new_6h_candle(self):
        config = DummyConfig()
        index_6h = pd.to_datetime(
            ["2026-01-01 00:00:00", "2026-01-01 06:00:00", "2026-01-01 12:00:00", "2026-01-01 18:00:00"]
        )
        df_6h = pd.DataFrame(
            {
                "high": [100, 101, 102, 108],
                "low": [99, 100, 101, 104],
                "close": [99.5, 100.5, 101.5, 107.0],
                "atr": [1.0, 1.0, 1.1, 1.3],
                "body_strength": [1.0, 1.1, 1.2, 1.9],
                "close_position": [0.55, 0.60, 0.65, 0.89],
                "vwap_distance_ratio": [0.01, 0.012, 0.013, 0.015],
                "range_expansion_factor": [0.9, 1.0, 1.05, 1.25],
            },
            index=index_6h,
        )
        df_12h = pd.DataFrame(
            {"close": [100, 109], "ema20": [99, 104], "ema50": [97, 101]},
            index=pd.to_datetime(["2026-01-01 00:00:00", "2026-01-01 12:00:00"]),
        )
        df_1d = pd.DataFrame(
            {"close": [99, 110], "ema20": [98, 104], "ema50": [96, 100]},
            index=pd.to_datetime(["2025-12-31 00:00:00", "2026-01-01 00:00:00"]),
        )
        execution_index = pd.to_datetime(
            ["2026-01-01 17:45:00", "2026-01-01 18:00:00", "2026-01-01 18:15:00"]
        )

        snapshots = build_h6_moonshot_snapshots(
            execution_index,
            df_6h,
            df_12h,
            df_1d,
            config=config,
        )

        self.assertFalse(bool(snapshots.loc[execution_index[0], "signal_event_long"]))
        self.assertTrue(bool(snapshots.loc[execution_index[1], "h6_new_candle"]))
        self.assertTrue(bool(snapshots.loc[execution_index[1], "signal_event_long"]))
        self.assertFalse(bool(snapshots.loc[execution_index[2], "signal_event_long"]))

    def test_h6_engine_builds_dormant_candidate_shape(self):
        config = DummyConfig()
        engine = H6MoonshotEngine(config=config)
        execution_row = pd.Series({"close": 107.0}, name=pd.Timestamp("2026-01-01 18:00:00"))
        snapshot = {
            "h6_new_candle": True,
            "signal_event_long": True,
            "h6_pass_structure_long": True,
            "h6_pass_shape_long": True,
            "h6_pass_12h_context_long": True,
            "h6_pass_1d_context_long": True,
            "h6_score_long": 0.82,
            "h6_stop_long": 103.0,
            "h6_body_strength": 1.9,
            "h6_range_expansion": 1.25,
            "h6_context_12h": "bullish",
            "signal_family_long": "h6_bridge_breakout",
        }

        candidate = engine.build_candidate(
            symbol="ETHUSDT",
            timestamp=execution_row.name,
            execution_row=execution_row,
            snapshot=snapshot,
            momentum_rank=0.75,
            top_symbols=[],
        )

        self.assertIsNotNone(candidate)
        self.assertEqual("h6_moonshot", candidate["strategy_type"])
        self.assertTrue(candidate["deferred_layer"])

    def test_h6_standard_engine_builds_looser_candidate_without_signal_event(self):
        config = DummyConfig()
        engine = H6StandardEngine(config=config)
        execution_row = pd.Series({"close": 107.0}, name=pd.Timestamp("2026-01-01 18:00:00"))
        snapshot = {
            "h6_new_candle": True,
            "signal_event_long": False,
            "h6_pass_structure_long": True,
            "h6_pass_shape_long": True,
            "h6_pass_12h_context_long": True,
            "h6_pass_1d_context_long": True,
            "h6_score_long": 0.70,
            "h6_stop_long": 103.0,
            "h6_body_strength": 1.7,
            "h6_range_expansion": 1.10,
            "h6_context_12h": "bullish",
            "signal_family_long": "h6_bridge_breakout",
        }

        candidate = engine.build_candidate(
            symbol="ETHUSDT",
            timestamp=execution_row.name,
            execution_row=execution_row,
            snapshot=snapshot,
            momentum_rank=0.75,
            top_symbols=["ETHUSDT"],
        )

        self.assertIsNotNone(candidate)
        self.assertEqual("h6_standard", candidate["strategy_type"])
        self.assertTrue(candidate["deferred_layer"])
        self.assertGreater(candidate["selection_score"], candidate["score"])

    def test_h6_symbol_filters_block_only_filtered_symbols(self):
        config = DummyConfig()
        config.data["strategy"]["h6_standard"]["allowed_symbols"] = ["ETHUSDT"]
        config.data["strategy"]["h6_standard"]["blocked_symbols"] = ["BTCUSDT"]
        engine = H6StandardEngine(config=config)
        execution_row = pd.Series({"close": 107.0}, name=pd.Timestamp("2026-01-01 18:00:00"))
        snapshot = {
            "h6_new_candle": True,
            "signal_event_long": False,
            "h6_pass_structure_long": True,
            "h6_pass_shape_long": True,
            "h6_pass_12h_context_long": True,
            "h6_pass_1d_context_long": True,
            "h6_score_long": 0.70,
            "h6_stop_long": 103.0,
            "h6_body_strength": 1.7,
            "h6_range_expansion": 1.10,
            "h6_context_12h": "bullish",
            "signal_family_long": "h6_bridge_breakout",
        }

        self.assertIsNotNone(
            engine.build_candidate(
                symbol="ETHUSDT",
                timestamp=execution_row.name,
                execution_row=execution_row,
                snapshot=snapshot,
                momentum_rank=0.75,
                top_symbols=[],
            )
        )
        self.assertIsNone(
            engine.build_candidate(
                symbol="BTCUSDT",
                timestamp=execution_row.name,
                execution_row=execution_row,
                snapshot=snapshot,
                momentum_rank=0.75,
                top_symbols=[],
            )
        )


if __name__ == "__main__":
    unittest.main()
