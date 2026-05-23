import unittest

import pandas as pd

from entry.breakout import BreakoutDetector
from entry.entry_engine import EntryEngine
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
            "block_compression": False,
            "blocked_scores": [],
            "min_body_strength_by_score": {},
            "blocked_upper_wick_ranges_by_score": {},
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
            "candle_metrics": {
                "average_body_period": 2,
            },
        },
        "strategy": {
            "sniffing": {
                "body_strength_min": 0.8,
                "close_position_min": 0.4,
                "upper_wick_max": 1.5,
                "min_confirmations": 1,
                "relax_after_r": 1.0,
                "relaxed_min_confirmations": 0,
                "slow_anchor_after_r": 2.0,
            },
            "pyramiding": {
                "max_total_risk_multiple": 1.0,
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
                "body_strength": 0.3,
                "upper_wick_ratio": 2.0,
                "close_position": 0.2,
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


if __name__ == "__main__":
    unittest.main()
