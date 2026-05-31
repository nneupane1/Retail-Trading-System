import unittest
import json
import tempfile

import pandas as pd

from entry.breakout import BreakoutDetector
from entry.edge_selector import EdgeSelector
from entry.entry_engine import EntryEngine
from entry.exploration_engine import ExplorationEngine
from entry.scoring import ScoreEngine
from exit.exit_engine import ExitEngine
from features.feature_pipeline import FeaturePipeline
from pyramiding.pyramiding_engine import PyramidingEngine
from sniffing.trend_sniffer import TrendSniffer


class DummyConfig:
    def __init__(self, data):
        self.data = data

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


def make_config():
    return DummyConfig({
        "entry": {
            "score_threshold": 4,
            "score_threshold_by_side": {},
            "block_compression": False,
            "block_compression_sides": ["long"],
            "blocked_scores": [],
            "blocked_scores_by_side": {},
            "min_body_strength_by_score": {},
            "blocked_upper_wick_ranges_by_score": {},
            "blocked_lower_wick_ranges_by_score": {},
            "conditional_filters_by_score": {},
            "directional_filters": {},
            "risk_multipliers_by_score": {},
            "allowed_entry_roles": None,
        },
        "features": {
            "ema_periods": {
                "fast": 2,
                "slow": 3,
            },
            "structure": {
                "high_period": 2,
                "low_period": 2,
            },
            "compression": {
                "fast_range_period": 2,
                "slow_range_period": 3,
                "ratio": 0.8,
            },
            "pressure": {
                "atr_baseline_period": 2,
                "cluster_lookback": 2,
                "failed_event_lookback": 2,
                "rejection_tolerance_atr": 0.35,
                "high_rejection_close_position_max": 0.45,
                "low_rejection_close_position_min": 0.55,
                "near_level_atr_multiple": 0.25,
                "ignition_body_strength_min": 1.8,
                "ignition_close_position_min": 0.75,
                "ignition_close_position_max": 0.25,
                "atr_compression_ratio_max": 0.9,
                "range_compression_ratio_max": 0.9,
            },
            "candle_metrics": {
                "average_body_period": 2,
            },
            "indicators": {
                "atr_period": 2,
                "macd_fast_period": 2,
                "macd_slow_period": 3,
                "macd_signal_period": 2,
                "bollinger_period": 2,
                "bollinger_std_dev": 2.0,
            },
        },
        "strategy": {
            "execution": {
                "mode": "legacy",
                "weighted": {
                    "score_weight": 0.7,
                    "momentum_weight": 0.3,
                    "noise_guard_min_strength": 0.25,
                    "min_entry_risk_multiplier": 0.25,
                    "max_strength_multiplier": 1.5,
                    "event_bonus": 1.1,
                    "non_event_bonus": 1.0,
                    "structural_floor_enabled": True,
                    "structural_floor_anchor_column": "ema3",
                    "bias_weights": {
                        "bullish": 1.15,
                        "neutral": 0.95,
                        "bearish": 0.7,
                    },
                    "regime_weights": {
                        "weak": 0.7,
                        "moderate": 1.0,
                        "strong": 1.2,
                    },
                    "momentum_component_weights": {
                        "price_to_fast_ema": 0.35,
                        "ema_gap": 0.25,
                        "vwap_distance": 0.2,
                        "macd_hist": 0.1,
                        "atr_rising": 0.1,
                    },
                    "momentum_scales": {
                        "price_to_fast_ema_ratio": 0.006,
                        "ema_gap_ratio": 0.004,
                        "vwap_distance_ratio": 0.004,
                        "macd_hist_atr_ratio": 0.25,
                    },
                },
            },
            "scoring": {
                "bias_weight": 2,
                "trend_weight": 1,
                "compression_weight": 1,
                "breakout_weight": 2,
                "breakdown_weight": 2,
                "body_strength_weight": 1,
                "close_position_weight": 1,
                "upper_wick_weight": 1,
                "lower_wick_weight": 1,
                "vwap_weight": 0,
                "atr_weight": 0,
                "macd_weight": 0,
                "bollinger_weight": 0,
                "body_strength_min": 1.3,
                "close_position_min": 0.6,
                "close_position_max": 0.4,
                "upper_wick_max": 1.0,
                "lower_wick_max": 1.0,
            },
            "sniffing": {
                "body_strength_min": 0.8,
                "close_position_min": 0.4,
                "close_position_max": 0.6,
                "upper_wick_max": 1.5,
                "lower_wick_max": 1.5,
                "min_confirmations": 1,
                "relax_after_r": 1.0,
                "relaxed_min_confirmations": 0,
                "slow_anchor_after_r": 2.0,
                "require_short_vwap_alignment": True,
                "support_alpha": {},
                "by_side": {},
                "trailing": {
                    "strong_body_min": 1.0,
                    "clean_wick_max": 1.0,
                    "min_vwap_distance": 0.0,
                    "min_ema_gap": 0.0,
                    "vwap_decay_threshold": 0.0015,
                    "ema_gap_decay_threshold": 0.0010,
                    "macd_decay_threshold": 0.0,
                    "body_decay_max": 0.8,
                    "wick_decay_min": 1.5,
                    "decay_close_position_max": 0.45,
                    "strong_close_position_min": 0.65,
                    "init_max_r": 0.5,
                    "confirmation_max_r": 1.5,
                    "expansion_min_momentum_signals": 4,
                    "decay_signal_threshold": 2,
                    "force_exit_decay_signal_threshold": 4,
                    "init_atr_buffer": 1.2,
                    "confirmation_atr_buffer": 0.9,
                    "expansion_atr_buffer": 1.8,
                    "decay_atr_buffer": 0.35,
                    "exit_atr_buffer": 0.15,
                    "expansion_anchor": "slow_ema",
                    "decay_anchor": "fast_ema",
                    "confirmation_anchor": "fast_ema",
                    "by_side": {
                        "short": {
                            "strong_close_position_max": 0.35,
                            "decay_close_position_min": 0.55,
                            "init_max_r": 0.35,
                            "confirmation_max_r": 1.0,
                            "expansion_min_momentum_signals": 3,
                            "force_exit_decay_signal_threshold": 3,
                            "init_atr_buffer": 1.0,
                            "confirmation_atr_buffer": 0.7,
                            "expansion_atr_buffer": 1.0,
                            "decay_atr_buffer": 0.25,
                            "exit_atr_buffer": 0.10,
                            "expansion_anchor": "fast_ema",
                            "decay_anchor": "fast_ema",
                        }
                    },
                },
            },
            "pyramiding": {
                "max_total_risk_multiple": 1.0,
                "allow_support_alpha": False,
                "quality_gate": {},
                "levels": [
                    {
                        "level": 1,
                        "r_multiple": 1,
                        "size_fraction": 0.5,
                    },
                    {
                        "level": 2,
                        "r_multiple": 2,
                        "size_fraction": 0.5,
                    },
                    {
                        "level": 3,
                        "r_multiple": 3,
                        "size_fraction": 0.25,
                    },
                ],
            },
            "directional": {
                "enabled_sides": ["long", "short"],
            },
            "exploration": {
                "enabled": False,
                "enabled_sides": ["long", "short"],
                "allow_neutral_bias": True,
                "block_opposite_bias": True,
                "require_atr_rising": True,
                "require_vwap_alignment": False,
                "require_macd_alignment": False,
                "minimum_regime_score": 2,
                "allowed_regime_classes": ["moderate", "strong"],
                "pressure_score_threshold": 4,
                "pressure_score_threshold_by_side": {"short": 4},
                "entry_risk_multiplier": 0.25,
                "entry_risk_multiplier_by_side": {"short": 0.2},
                "entry_priority": 0,
                "entry_role": "support",
            },
        },
    })


class FeaturePipelineTests(unittest.TestCase):
    def test_breakout_is_only_marked_on_state_transition(self):
        df = pd.DataFrame(
            {
                "open": [9.8, 9.9, 10.0, 11.0],
                "high": [10.0, 10.0, 11.0, 12.0],
                "low": [9.7, 9.8, 9.9, 10.9],
                "close": [9.9, 10.0, 11.1, 12.1],
                "volume": [100, 100, 100, 100],
            },
            index=pd.date_range("2026-01-01", periods=4, freq="15min"),
        )

        result = FeaturePipeline(config=make_config()).compute(df)

        self.assertEqual(len(result), 2)
        self.assertEqual(result.index[0], pd.Timestamp("2026-01-01 00:30:00"))
        self.assertFalse(result[[
            "hh2",
            "ll2",
            "range_2",
            "range_3",
            "prev_close",
            "hh2_prev",
            "body_strength",
            "upper_wick_ratio",
            "lower_wick_ratio",
            "close_position",
        ]].isna().any().any())
        self.assertEqual(result["prev_close"].iloc[0], 10.0)
        self.assertTrue(result["above_breakout_level"].iloc[0])
        self.assertTrue(result["above_breakout_level"].iloc[1])
        self.assertTrue(result["breakout"].iloc[0])
        self.assertFalse(result["breakout"].iloc[1])
        self.assertFalse(result["breakdown"].iloc[0])

    def test_pressure_model_columns_are_built(self):
        df = pd.DataFrame(
            {
                "open": [10.0, 9.9, 9.95, 10.02, 10.08, 10.2],
                "high": [10.3, 10.15, 10.12, 10.14, 10.18, 10.55],
                "low": [9.8, 9.82, 9.88, 9.94, 10.0, 10.1],
                "close": [9.9, 9.95, 10.0, 10.04, 10.12, 10.5],
                "volume": [100, 100, 100, 100, 100, 100],
            },
            index=pd.date_range("2026-01-01", periods=6, freq="15min"),
        )

        result = FeaturePipeline(config=make_config()).compute(df)

        for column in [
            "range_compression_ratio",
            "atr_compression_ratio",
            "resistance_rejection_count",
            "support_rejection_count",
            "failed_breakout_up_count",
            "failed_breakdown_down_count",
            "pressure_score_long",
            "pressure_score_short",
            "pressure_ignition_long",
            "pressure_ignition_short",
        ]:
            self.assertIn(column, result.columns)


class ScoreEngineTests(unittest.TestCase):
    def test_score_engine_exposes_component_breakdown_and_normalized_strength(self):
        engine = ScoreEngine(config=make_config())
        row = pd.Series(
            {
                "close": 101.0,
                "ema2": 100.0,
                "compression": True,
                "breakout": True,
                "breakdown": False,
                "body_strength": 1.8,
                "close_position": 0.9,
                "upper_wick_ratio": 0.2,
                "lower_wick_ratio": 0.1,
                "session_vwap": 100.5,
            }
        )

        details = engine.compute_score_details(row, bias="bullish", side="long")

        self.assertEqual(details["score"], 9.0)
        self.assertAlmostEqual(details["normalized_score"], 1.0)
        self.assertEqual(details["max_score"], 9.0)
        self.assertTrue(details["components"]["event"]["aligned"])
        self.assertEqual(details["components"]["event"]["points"], 2.0)

    def test_score_engine_short_breakdown_uses_directional_thresholds(self):
        engine = ScoreEngine(config=make_config())
        row = pd.Series(
            {
                "close": 98.0,
                "ema2": 99.5,
                "compression": False,
                "breakout": False,
                "breakdown": True,
                "body_strength": 1.5,
                "close_position": 0.2,
                "upper_wick_ratio": 0.4,
                "lower_wick_ratio": 0.2,
                "session_vwap": 99.0,
            }
        )

        details = engine.compute_score_details(row, bias="bearish", side="short")

        self.assertEqual(details["score"], 8.0)
        self.assertAlmostEqual(details["normalized_score"], 8.0 / 9.0)
        self.assertTrue(details["components"]["wick"]["aligned"])
        self.assertLess(details["components"]["close_position"]["value"], 0.4)


class BreakoutDetectorTests(unittest.TestCase):
    def test_breakout_requires_cross_from_below_current_level(self):
        detector = BreakoutDetector(config=make_config())

        breakout_row = pd.Series(
            {
                "close": 101.0,
                "prev_close": 99.0,
                "hh2_prev": 100.0,
            }
        )
        extended_row = pd.Series(
            {
                "close": 102.0,
                "prev_close": 101.0,
                "hh2_prev": 100.0,
            }
        )

        self.assertTrue(detector.is_breakout(breakout_row))
        self.assertFalse(detector.is_breakout(extended_row))

    def test_breakout_detector_fails_without_previous_close(self):
        detector = BreakoutDetector(config=make_config())

        row = pd.Series(
            {
                "close": 101.0,
                "hh2_prev": 100.0,
            }
        )

        with self.assertRaises(KeyError):
            detector.is_breakout(row)


class EntryEngineTests(unittest.TestCase):
    def test_entry_engine_can_block_compressed_setups(self):
        config = make_config()
        config.data["entry"]["block_compression"] = True
        engine = EntryEngine(config=config)
        row = pd.Series(
            {
                "close": 101.0,
                "compression": True,
                "breakout": True,
                "ll2": 95.0,
            },
            name=pd.Timestamp("2026-01-01 00:00:00"),
        )

        trade = engine.generate_entry(row, score=6, bias="bullish")

        self.assertIsNone(trade)

    def test_entry_engine_can_block_specific_score_buckets(self):
        config = make_config()
        config.data["entry"]["blocked_scores"] = [7]
        engine = EntryEngine(config=config)
        row = pd.Series(
            {
                "close": 101.0,
                "compression": False,
                "breakout": True,
                "ll2": 95.0,
            },
            name=pd.Timestamp("2026-01-01 00:00:00"),
        )

        trade = engine.generate_entry(row, score=7, bias="bullish")

        self.assertIsNone(trade)

    def test_entry_engine_can_require_stronger_body_for_specific_scores(self):
        config = make_config()
        config.data["entry"]["min_body_strength_by_score"] = {"8": 2.0}
        engine = EntryEngine(config=config)
        row = pd.Series(
            {
                "close": 101.0,
                "compression": False,
                "breakout": True,
                "body_strength": 1.7,
                "ll2": 95.0,
            },
            name=pd.Timestamp("2026-01-01 00:00:00"),
        )

        trade = engine.generate_entry(row, score=8, bias="bullish")

        self.assertIsNone(trade)

    def test_entry_engine_can_block_upper_wick_ranges_for_specific_scores(self):
        config = make_config()
        config.data["entry"]["blocked_upper_wick_ranges_by_score"] = {
            "8": [{"min": 0.1, "max": 0.3}],
        }
        engine = EntryEngine(config=config)
        row = pd.Series(
            {
                "close": 101.0,
                "compression": False,
                "breakout": True,
                "body_strength": 2.3,
                "upper_wick_ratio": 0.2,
                "ll2": 95.0,
            },
            name=pd.Timestamp("2026-01-01 00:00:00"),
        )

        trade = engine.generate_entry(row, score=8, bias="bullish")

        self.assertIsNone(trade)

    def test_entry_engine_can_generate_short_trade(self):
        config = make_config()
        engine = EntryEngine(config=config)
        row = pd.Series(
            {
                "close": 99.0,
                "compression": False,
                "breakdown": True,
                "hh2": 105.0,
                "body_strength": 1.8,
                "lower_wick_ratio": 0.2,
                "close_position": 0.2,
            },
            name=pd.Timestamp("2026-01-01 00:00:00"),
        )

        trade = engine.generate_entry(row, score=6, bias="bearish", side="short")

        self.assertIsNotNone(trade)
        self.assertEqual(trade.side, "short")
        self.assertEqual(trade.stop, 105.0)
        self.assertEqual(trade.entry_risk_multiplier, 1.0)

    def test_entry_engine_can_apply_conditional_score_filters(self):
        config = make_config()
        config.data["entry"]["conditional_filters_by_score"] = {
            "5": {
                "long": {
                    "min_body_strength": 1.6,
                    "max_upper_wick_ratio": 0.5,
                    "min_close_position": 0.7,
                    "min_abs_fast_ema_slope_ratio": 0.001,
                    "require_vwap_alignment": True,
                }
            }
        }
        engine = EntryEngine(config=config)
        row = pd.Series(
            {
                "close": 101.0,
                "compression": False,
                "breakout": True,
                "body_strength": 1.5,
                "upper_wick_ratio": 0.3,
                "close_position": 0.8,
                "fast_ema_slope_ratio": 0.002,
                "session_vwap": 100.0,
                "ll2": 95.0,
            },
            name=pd.Timestamp("2026-01-01 00:00:00"),
        )

        trade = engine.generate_entry(row, score=5, bias="bullish")

        self.assertIsNone(trade)

    def test_entry_engine_can_apply_regime_conditioned_score_filters(self):
        config = make_config()
        config.data["entry"]["conditional_filters_by_score"] = {
            "5": {
                "long": {
                    "allowed_regime_classes": ["strong"],
                    "min_metric_values": {
                        "regime_score": 4,
                        "upper_wick_ratio": 3.0,
                        "vwap_distance_ratio": 0.002,
                    },
                    "max_close_position": 0.45,
                }
            }
        }
        engine = EntryEngine(config=config)
        row = pd.Series(
            {
                "close": 101.0,
                "compression": False,
                "breakout": True,
                "body_strength": 0.7,
                "upper_wick_ratio": 3.5,
                "close_position": 0.35,
                "vwap_distance_ratio": 0.003,
                "ll2": 95.0,
            },
            name=pd.Timestamp("2026-01-01 00:00:00"),
        )

        blocked = engine.generate_entry(
            row,
            score=5,
            bias="bullish",
            regime_score=3,
            regime_class="strong",
        )
        allowed = engine.generate_entry(
            row,
            score=5,
            bias="bullish",
            regime_score=4,
            regime_class="strong",
        )

        self.assertIsNone(blocked)
        self.assertIsNotNone(allowed)

    def test_entry_engine_can_use_higher_short_threshold(self):
        config = make_config()
        config.data["entry"]["score_threshold_by_side"] = {"short": 9}
        engine = EntryEngine(config=config)
        row = pd.Series(
            {
                "close": 99.0,
                "compression": False,
                "breakdown": True,
                "hh2": 105.0,
                "body_strength": 1.8,
                "lower_wick_ratio": 0.2,
                "close_position": 0.2,
            },
            name=pd.Timestamp("2026-01-01 00:00:00"),
        )

        trade = engine.generate_entry(row, score=8, bias="bearish", side="short")

        self.assertIsNone(trade)

    def test_entry_engine_can_assign_score_specific_risk_multiplier(self):
        config = make_config()
        config.data["entry"]["risk_multipliers_by_score"] = {
            "5": {"long": 0.5}
        }
        engine = EntryEngine(config=config)
        row = pd.Series(
            {
                "close": 101.0,
                "compression": False,
                "breakout": True,
                "body_strength": 1.7,
                "upper_wick_ratio": 0.3,
                "close_position": 0.8,
                "ll2": 95.0,
            },
            name=pd.Timestamp("2026-01-01 00:00:00"),
        )

        trade = engine.generate_entry(row, score=5, bias="bullish", side="long")

        self.assertIsNotNone(trade)
        self.assertEqual(trade.entry_risk_multiplier, 0.5)

    def test_entry_engine_can_restrict_allowed_roles(self):
        config = make_config()
        config.data["entry"]["risk_multipliers_by_score"] = {
            "5": {"long": 0.5}
        }
        config.data["entry"]["allowed_entry_roles"] = ["support"]
        engine = EntryEngine(config=config)
        row = pd.Series(
            {
                "close": 101.0,
                "compression": False,
                "breakout": True,
                "body_strength": 1.7,
                "upper_wick_ratio": 0.3,
                "close_position": 0.8,
                "ll2": 95.0,
            },
            name=pd.Timestamp("2026-01-01 00:00:00"),
        )

        blocked = engine.generate_entry(row, score=6, bias="bullish", side="long")
        allowed = engine.generate_entry(row, score=5, bias="bullish", side="long")

        self.assertIsNone(blocked)
        self.assertIsNotNone(allowed)
        self.assertEqual(allowed.entry_role, "support")

    def test_entry_engine_can_apply_directional_short_filters(self):
        config = make_config()
        config.data["entry"]["directional_filters"] = {
            "short": {
                "min_metric_values": {
                    "macd_hist": -40.0,
                },
                "max_metric_values": {
                    "vwap_distance_ratio": -0.002,
                },
            }
        }
        engine = EntryEngine(config=config)
        row = pd.Series(
            {
                "close": 99.0,
                "compression": False,
                "breakdown": True,
                "hh2": 105.0,
                "body_strength": 1.8,
                "lower_wick_ratio": 0.2,
                "close_position": 0.2,
                "macd_hist": -60.0,
                "vwap_distance_ratio": -0.001,
            },
            name=pd.Timestamp("2026-01-01 00:00:00"),
        )

        trade = engine.generate_entry(row, score=9, bias="bearish", side="short")

        self.assertIsNone(trade)

    def test_weighted_entry_engine_builds_continuous_long_candidate(self):
        config = make_config()
        config.data["strategy"]["execution"]["mode"] = "weighted"
        engine = EntryEngine(config=config)
        row = pd.Series(
            {
                "close": 104.0,
                "ema2": 102.0,
                "ema3": 100.0,
                "breakout": False,
                "body_strength": 1.5,
                "upper_wick_ratio": 0.2,
                "close_position": 0.8,
                "price_to_fast_ema_ratio": 0.01,
                "ema_gap_ratio": 0.01,
                "vwap_distance_ratio": 0.01,
                "atr_rising": True,
                "atr": 2.0,
                "macd_hist": 0.6,
                "ll2": 97.0,
            },
            name=pd.Timestamp("2026-01-01 00:00:00"),
        )

        profile = engine.evaluate_weighted_opportunity(
            row,
            score=5,
            bias="neutral",
            side="long",
            regime_score=2,
            regime_class="moderate",
        )

        self.assertTrue(profile["eligible"])
        self.assertGreater(profile["final_strength"], 0.25)
        self.assertIsNotNone(profile["candidate"])
        self.assertEqual(profile["candidate"]["entry_role"], "core")
        self.assertAlmostEqual(
            profile["candidate"]["trade"].final_strength,
            profile["final_strength"],
        )

    def test_weighted_entry_engine_can_use_precomputed_normalized_score(self):
        config = make_config()
        config.data["strategy"]["execution"]["mode"] = "weighted"
        engine = EntryEngine(config=config)
        row = pd.Series(
            {
                "close": 104.0,
                "ema2": 102.0,
                "ema3": 100.0,
                "breakout": False,
                "body_strength": 1.5,
                "upper_wick_ratio": 0.2,
                "close_position": 0.8,
                "price_to_fast_ema_ratio": 0.01,
                "ema_gap_ratio": 0.01,
                "vwap_distance_ratio": 0.01,
                "atr_rising": True,
                "atr": 2.0,
                "macd_hist": 0.6,
                "ll2": 97.0,
            },
            name=pd.Timestamp("2026-01-01 00:00:00"),
        )

        profile = engine.evaluate_weighted_opportunity(
            row,
            score=8,
            bias="neutral",
            side="long",
            regime_score=2,
            regime_class="moderate",
            score_details={
                "normalized_score": 0.2,
                "max_score": 9.0,
                "components": {"bias": {"points": 0.0, "weight": 2.0}},
            },
        )

        self.assertAlmostEqual(profile["score_norm"], 0.2)
        self.assertEqual(profile["score_max"], 9.0)
        self.assertIn("bias", profile["score_components"])

    def test_weighted_entry_engine_rejects_candidate_below_structural_floor(self):
        config = make_config()
        config.data["strategy"]["execution"]["mode"] = "weighted"
        engine = EntryEngine(config=config)
        row = pd.Series(
            {
                "close": 98.0,
                "ema2": 99.0,
                "ema3": 100.0,
                "breakout": True,
                "body_strength": 1.5,
                "upper_wick_ratio": 0.2,
                "close_position": 0.8,
                "price_to_fast_ema_ratio": -0.01,
                "ema_gap_ratio": -0.01,
                "vwap_distance_ratio": -0.01,
                "atr_rising": True,
                "atr": 2.0,
                "macd_hist": -0.6,
                "ll2": 95.0,
            },
            name=pd.Timestamp("2026-01-01 00:00:00"),
        )

        profile = engine.evaluate_weighted_opportunity(
            row,
            score=6,
            bias="bullish",
            side="long",
            regime_score=3,
            regime_class="strong",
        )

        self.assertFalse(profile["eligible"])
        self.assertEqual(profile["rejection_reason"], "structural_floor")
        self.assertIsNone(profile["candidate"])


class ExplorationEngineTests(unittest.TestCase):
    def test_exploration_engine_can_build_long_candidate(self):
        config = make_config()
        config.data["strategy"]["exploration"]["enabled"] = True
        engine = ExplorationEngine(config=config)
        row = pd.Series(
            {
                "close": 101.0,
                "atr_rising": True,
                "pressure_score_long": 5,
                "pressure_ignition_long": True,
                "ll2": 95.0,
            },
            name=pd.Timestamp("2026-01-01 00:00:00"),
        )

        candidate = engine.build_candidate(
            row,
            bias="neutral",
            side="long",
            regime_score=3,
            regime_class="strong",
        )

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["signal_family"], "exploratory")
        self.assertEqual(candidate["trade"].signal_family, "exploratory")
        self.assertEqual(candidate["trade"].entry_role, "support")
        self.assertEqual(candidate["trade"].pressure_score, 5)

    def test_exploration_engine_blocks_opposite_bias(self):
        config = make_config()
        config.data["strategy"]["exploration"]["enabled"] = True
        engine = ExplorationEngine(config=config)
        row = pd.Series(
            {
                "close": 101.0,
                "atr_rising": True,
                "pressure_score_long": 5,
                "pressure_ignition_long": True,
                "ll2": 95.0,
            },
            name=pd.Timestamp("2026-01-01 00:00:00"),
        )

        candidate = engine.build_candidate(
            row,
            bias="bearish",
            side="long",
            regime_score=3,
            regime_class="strong",
        )

        self.assertIsNone(candidate)


class TrendSnifferTests(unittest.TestCase):
    def test_trend_can_stay_alive_with_partial_strength(self):
        row = pd.Series(
            {
                "close": 105.0,
                "ema2": 100.0,
                "body_strength": 0.5,
                "upper_wick_ratio": 0.8,
                "close_position": 0.3,
            }
        )

        sniffer = TrendSniffer(config=make_config())

        self.assertTrue(sniffer.is_trend_alive(row))

    def test_profitable_trade_can_relax_candle_quality_if_price_holds_ema(self):
        row = pd.Series(
            {
                "close": 110.0,
                "ema2": 100.0,
                "body_strength": 0.3,
                "upper_wick_ratio": 2.0,
                "close_position": 0.2,
            }
        )
        trade = type("TradeStub", (), {"entry_price": 100.0, "R": 5.0})()

        sniffer = TrendSniffer(config=make_config())

        self.assertTrue(sniffer.is_trend_alive(row, trade=trade))

    def test_elite_trade_can_switch_to_slower_ema_anchor(self):
        row = pd.Series(
            {
                "close": 108.0,
                "ema2": 109.0,
                "ema3": 100.0,
                "body_strength": 1.2,
                "upper_wick_ratio": 0.4,
                "close_position": 0.8,
                "vwap_distance_ratio": 0.01,
                "ema_gap_ratio": 0.02,
                "macd_hist": 0.5,
            }
        )
        trade = type("TradeStub", (), {"entry_price": 100.0, "R": 4.0})()

        sniffer = TrendSniffer(config=make_config())

        self.assertTrue(sniffer.is_trend_alive(row, trade=trade))

    def test_trend_dies_when_price_loses_ema_anchor(self):
        row = pd.Series(
            {
                "close": 99.0,
                "ema2": 100.0,
                "body_strength": 1.2,
                "upper_wick_ratio": 0.5,
                "close_position": 0.8,
            }
        )

        sniffer = TrendSniffer(config=make_config())

        self.assertFalse(sniffer.is_trend_alive(row))

    def test_short_trend_requires_price_below_anchor_and_vwap(self):
        row = pd.Series(
            {
                "close": 95.0,
                "ema2": 100.0,
                "session_vwap": 99.0,
                "body_strength": 1.0,
                "lower_wick_ratio": 0.2,
                "close_position": 0.2,
            }
        )
        trade = type("TradeStub", (), {"entry_price": 100.0, "R": 5.0, "side": "short"})()

        sniffer = TrendSniffer(config=make_config())

        self.assertTrue(sniffer.is_trend_alive(row, trade=trade))

    def test_short_trend_can_use_stricter_side_specific_confirmation_count(self):
        config = make_config()
        config.data["strategy"]["sniffing"]["by_side"] = {
            "short": {
                "min_confirmations": 3,
                "relax_after_r": 2.0,
            }
        }
        row = pd.Series(
            {
                "close": 97.0,
                "ema2": 100.0,
                "session_vwap": 99.0,
                "body_strength": 1.0,
                "lower_wick_ratio": 0.2,
                "close_position": 0.7,
            }
        )
        trade = type("TradeStub", (), {"entry_price": 100.0, "R": 5.0, "side": "short"})()

        sniffer = TrendSniffer(config=config)

        self.assertFalse(sniffer.is_trend_alive(row, trade=trade))

    def test_support_alpha_trade_can_disable_relaxed_hold_logic(self):
        config = make_config()
        config.data["strategy"]["sniffing"]["support_alpha"] = {
            "min_confirmations": 2,
            "relax_after_r": None,
            "slow_anchor_after_r": None,
        }
        row = pd.Series(
            {
                "close": 110.0,
                "ema2": 100.0,
                "body_strength": 0.3,
                "upper_wick_ratio": 2.0,
                "close_position": 0.2,
            }
        )
        trade = type(
            "TradeStub",
            (),
            {
                "entry_price": 100.0,
                "R": 5.0,
                "entry_risk_multiplier": 0.5,
            },
        )()

        sniffer = TrendSniffer(config=config)

        self.assertFalse(sniffer.is_trend_alive(row, trade=trade))

    def test_trailing_state_can_tighten_long_stop_during_decay(self):
        row = pd.Series(
            {
                "close": 112.0,
                "ema2": 110.0,
                "ema3": 106.0,
                "ll2": 108.0,
                "session_vwap": 109.5,
                "atr": 2.0,
                "body_strength": 0.7,
                "upper_wick_ratio": 1.8,
                "close_position": 0.55,
                "vwap_distance_ratio": 0.0005,
                "ema_gap_ratio": 0.0025,
                "macd_hist": 0.3,
            }
        )
        trade = type(
            "TradeStub",
            (),
            {
                "entry_price": 100.0,
                "R": 5.0,
                "side": "long",
                "stop": 95.0,
                "stop_column": "ll2",
                "active_stop": 95.0,
                "entry_risk_multiplier": 1.0,
            },
        )()

        sniffer = TrendSniffer(config=make_config())
        result = sniffer.evaluate(row, trade=trade)

        self.assertEqual(result["state"], "decay")
        self.assertFalse(result["should_exit"])
        self.assertGreater(result["proposed_stop"], 95.0)

    def test_trailing_state_can_force_short_exit_on_behavior_break(self):
        row = pd.Series(
            {
                "close": 95.0,
                "ema2": 96.0,
                "ema3": 97.0,
                "hh2": 98.0,
                "session_vwap": 94.2,
                "atr": 1.5,
                "body_strength": 0.7,
                "lower_wick_ratio": 1.6,
                "close_position": 0.7,
                "vwap_distance_ratio": -0.0002,
                "ema_gap_ratio": -0.0004,
                "macd_hist": -0.05,
            }
        )
        trade = type(
            "TradeStub",
            (),
            {
                "entry_price": 100.0,
                "R": 4.0,
                "side": "short",
                "stop": 104.0,
                "stop_column": "hh2",
                "active_stop": 104.0,
                "entry_risk_multiplier": 1.0,
            },
        )()

        sniffer = TrendSniffer(config=make_config())
        result = sniffer.evaluate(row, trade=trade)

        self.assertEqual(result["state"], "exit")
        self.assertTrue(result["should_exit"])


class ExitEngineTests(unittest.TestCase):
    def test_intrabar_stop_touch_triggers_exit_even_if_close_recovers(self):
        engine = ExitEngine()
        row = pd.Series(
            {
                "low": 89.0,
                "close": 95.0,
            }
        )

        self.assertTrue(engine.should_exit(row, stop_price=90.0))

    def test_close_price_fallback_preserves_compatibility_when_low_is_missing(self):
        engine = ExitEngine()
        row = pd.Series(
            {
                "close": 89.0,
            }
        )

        self.assertTrue(engine.should_exit(row, stop_price=90.0))

    def test_no_exit_when_intrabar_low_stays_above_stop(self):
        engine = ExitEngine()
        row = pd.Series(
            {
                "low": 91.0,
                "close": 95.0,
            }
        )

        self.assertFalse(engine.should_exit(row, stop_price=90.0))

    def test_short_exit_triggers_when_intrabar_high_touches_stop(self):
        engine = ExitEngine()
        row = pd.Series(
            {
                "high": 111.0,
                "close": 109.0,
            }
        )

        self.assertTrue(engine.should_exit(row, stop_price=110.0, side="short"))


class PyramidingEngineTests(unittest.TestCase):
    def test_pyramiding_is_blocked_when_trend_is_not_healthy(self):
        engine = PyramidingEngine(config=make_config())

        blocked_level = engine.check_pyramiding(
            price=110.0,
            entry_price=100.0,
            R=5.0,
            current_level=0,
            trend_ok=False,
            previous_price=104.0,
        )
        allowed_level = engine.check_pyramiding(
            price=110.0,
            entry_price=100.0,
            R=5.0,
            current_level=0,
            trend_ok=True,
            previous_price=104.0,
        )

        self.assertEqual(blocked_level, 0)
        self.assertEqual(allowed_level, 1)

    def test_pyramiding_requires_cross_event_not_just_price_above_level(self):
        engine = PyramidingEngine(config=make_config())

        no_cross_level = engine.check_pyramiding(
            price=110.0,
            entry_price=100.0,
            R=5.0,
            current_level=0,
            trend_ok=True,
            previous_price=106.0,
        )

        self.assertEqual(no_cross_level, 0)

    def test_pyramiding_can_trigger_third_level_after_second_level(self):
        engine = PyramidingEngine(config=make_config())

        third_level = engine.check_pyramiding(
            price=116.0,
            entry_price=100.0,
            R=5.0,
            current_level=2,
            trend_ok=True,
            previous_price=114.0,
        )

        self.assertEqual(third_level, 3)

    def test_pyramiding_quality_gate_blocks_weak_trade(self):
        config = make_config()
        config.data["strategy"]["pyramiding"]["quality_gate"] = {
            "enabled": True,
            "body_strength_min": 1.5,
            "upper_wick_max": 0.6,
            "close_position_min": 0.75,
            "min_confirmations": 2,
            "min_open_r_multiple": 1.0,
            "max_total_risk_multiple": 2.5,
        }
        engine = PyramidingEngine(config=config)
        row = pd.Series(
            {
                "close": 110.0,
                "body_strength": 1.0,
                "upper_wick_ratio": 0.7,
                "close_position": 0.7,
            }
        )
        trade = type("TradeStub", (), {"entry_price": 100.0, "R": 5.0})()

        self.assertFalse(engine.qualifies_for_pyramiding(row, trade))

    def test_short_pyramiding_triggers_on_downside_cross(self):
        engine = PyramidingEngine(config=make_config())

        new_level = engine.check_pyramiding(
            price=94.0,
            entry_price=100.0,
            R=5.0,
            current_level=0,
            trend_ok=True,
            previous_price=96.0,
            side="short",
        )

        self.assertEqual(new_level, 1)

    def test_quality_gate_can_unlock_larger_pyramid_risk_budget(self):
        config = make_config()
        config.data["strategy"]["pyramiding"]["quality_gate"] = {
            "enabled": True,
            "max_total_risk_multiple": 2.5,
        }
        engine = PyramidingEngine(config=config)

        blocked_size = engine.cap_add_size_by_risk(
            add_size=0.5,
            add_price=110.0,
            stop_price=100.0,
            current_total_risk=10.0,
            equity=1000.0,
            risk_per_trade=0.01,
            quality_gate_passed=False,
        )
        unlocked_size = engine.cap_add_size_by_risk(
            add_size=0.5,
            add_price=110.0,
            stop_price=100.0,
            current_total_risk=10.0,
            equity=1000.0,
            risk_per_trade=0.01,
            quality_gate_passed=True,
        )

        self.assertEqual(blocked_size, 0)
        self.assertGreater(unlocked_size, 0)

    def test_quality_gate_can_scale_level_two_add_size(self):
        config = make_config()
        config.data["strategy"]["pyramiding"]["quality_gate"] = {
            "enabled": True,
            "size_fraction_multipliers_by_level": {
                "2": 1.5,
            },
        }
        engine = PyramidingEngine(config=config)

        normal_size = engine.get_pyramid_size(
            base_size=1.0,
            level=2,
            quality_gate_passed=False,
        )
        elite_size = engine.get_pyramid_size(
            base_size=1.0,
            level=2,
            quality_gate_passed=True,
        )

        self.assertEqual(normal_size, 0.5)
        self.assertEqual(elite_size, 0.75)

    def test_support_alpha_trade_can_be_blocked_from_pyramiding(self):
        config = make_config()
        blocked_engine = PyramidingEngine(config=config)
        allowed_config = make_config()
        allowed_config.data["strategy"]["pyramiding"]["allow_support_alpha"] = True
        allowed_engine = PyramidingEngine(config=allowed_config)
        trade = type(
            "TradeStub",
            (),
            {
                "entry_price": 100.0,
                "R": 5.0,
                "entry_risk_multiplier": 0.5,
            },
        )()

        self.assertFalse(blocked_engine.qualifies_for_pyramiding(pd.Series({}), trade))
        self.assertTrue(allowed_engine.qualifies_for_pyramiding(pd.Series({}), trade))

    def test_edge_selector_reads_small_bucket_table_and_returns_valid_bucket(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            edge_table_path = f"{temp_dir}/edge_table.json"
            with open(edge_table_path, "w", encoding="utf-8") as file_handle:
                json.dump(
                    {
                        "metadata": {"min_count": 300, "min_avg_return_net": 0.0},
                        "buckets": {
                            "momentum_long|bullish|strong|near": {
                                "valid": True,
                                "expected_return": 0.0015,
                                "risk_mult": 1.2,
                                "signal_count": 420,
                                "selected_horizon": 3,
                            }
                        },
                    },
                    file_handle,
                )

            config = make_config()
            config.data["strategy"]["edge_selection"] = {
                "enabled": True,
                "table_path": edge_table_path,
                "strong_body_threshold": 1.3,
                "vwap_far_threshold": 0.01,
                "min_expected_return": 0.0,
                "default_risk_mult": 1.0,
                "max_risk_mult": 1.5,
            }
            selector = EdgeSelector(config=config)
            row = pd.Series(
                {
                    "breakout": True,
                    "breakdown": False,
                    "compression": False,
                    "body_strength": 1.7,
                    "close_position": 0.85,
                    "vwap_distance_ratio": 0.002,
                    "upper_wick_ratio": 0.2,
                    "lower_wick_ratio": 0.2,
                }
            )
            profile = selector.evaluate(row, bias="bullish", side="long")

            self.assertTrue(profile["bucket_valid"])
            self.assertEqual(profile["bucket_key_text"], "momentum_long|bullish|strong|near")
            self.assertAlmostEqual(profile["bucket_expected_return"], 0.0015)
            self.assertAlmostEqual(profile["bucket_risk_mult"], 1.2)


if __name__ == "__main__":
    unittest.main()
