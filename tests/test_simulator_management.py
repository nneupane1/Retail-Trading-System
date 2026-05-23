import unittest

import pandas as pd

from simulation.simulator import Simulator


class DummyConfig:
    def get(self, *keys, default=None):
        if keys == ("strategy", "directional", "enabled_sides"):
            return ["long", "short"]
        return default

    def require(self, *keys):
        if keys == ("entry", "score_threshold"):
            return 4
        if keys == ("account", "risk_per_trade"):
            return 0.01
        if keys == ("features", "structure", "high_period"):
            return 2
        if keys == ("features", "structure", "low_period"):
            return 2
        raise KeyError(f"Unexpected config lookup: {keys}")


class SideRiskConfig(DummyConfig):
    def get(self, *keys, default=None):
        if keys == ("account", "risk_per_trade_by_side"):
            return {"short": 0.005}
        return super().get(*keys, default=default)


class ShortThresholdConfig(DummyConfig):
    def get(self, *keys, default=None):
        if keys == ("entry", "score_threshold_by_side"):
            return {"short": 9}
        return super().get(*keys, default=default)


class StaticBiasDetector:
    def get_bias(self, df_1h):
        return "bullish"


class StaticRegimeDetector:
    def compute_regime(self, df_5h, df_12h, side="long"):
        return None


class ContextRegimeDetector:
    def compute_regime(self, df_5h, df_12h, side="long"):
        return 3

    def classify(self, regime_score):
        return "strong"


class BlockingRegimeDetector:
    def compute_regime(self, df_5h, df_12h, side="long"):
        return 1

    def allows_entries(self, regime_score):
        return False


class StaticScoreEngine:
    def compute_score(self, row, bias, side="long"):
        return 0


class PositiveScoreEngine:
    def compute_score(self, row, bias, side="long"):
        return 5 if side == "long" else 0


class MixedThresholdScoreEngine:
    def compute_score(self, row, bias, side="long"):
        return 5 if side == "long" else 8


class OverrideScoreEngine:
    def compute_score(self, row, bias, side="long"):
        return 6 if side == "long" else 0


class NullEntryEngine:
    def generate_entry(
        self,
        row,
        score,
        bias,
        side="long",
        regime_score=None,
        regime_class=None,
    ):
        return None


class DummyPositionSizer:
    def calculate(self, **kwargs):
        return 1.0


class RecordingPositionSizer:
    def __init__(self):
        self.calls = []

    def calculate(self, **kwargs):
        self.calls.append(kwargs)
        return 1.0


class RecordingEquityLogger:
    def __init__(self):
        self.calls = []

    def log(self, timestamp, equity):
        self.calls.append((timestamp, equity))


class ZeroPositionSizer:
    def calculate(self, **kwargs):
        return 0.0


class FixedEntryEngine:
    def __init__(self, entry_risk_multiplier=1.0):
        self.trade = DummyTrade()
        self.calls = 0
        self.trade.entry_risk_multiplier = entry_risk_multiplier

    def generate_entry(
        self,
        row,
        score,
        bias,
        side="long",
        regime_score=None,
        regime_class=None,
    ):
        self.calls += 1
        self.trade.side = side
        return self.trade


class ThresholdAwareEntryEngine:
    def preview_entry_metadata(self, score, side):
        return {
            "entry_threshold": 9 if side == "short" else 4,
            "entry_risk_multiplier": 1.0,
            "entry_role": "core",
            "entry_priority": 1,
        }

    def generate_entry(
        self,
        row,
        score,
        bias,
        side="long",
        regime_score=None,
        regime_class=None,
    ):
        trade = DummyTrade()
        trade.side = side
        trade.entry_role = "core"
        trade.entry_priority = 1
        return trade


class OverrideAwareEntryEngine:
    def preview_entry_metadata(self, score, side):
        is_support = side == "long" and score <= 5
        return {
            "entry_threshold": 4,
            "entry_risk_multiplier": 0.5 if is_support else 1.0,
            "entry_role": "support" if is_support else "core",
            "entry_priority": 0 if is_support else 1,
        }

    def generate_entry(
        self,
        row,
        score,
        bias,
        side="long",
        regime_score=None,
        regime_class=None,
    ):
        trade = DummyTrade()
        trade.side = side
        trade.entry_risk_multiplier = 0.5 if side == "long" and score <= 5 else 1.0
        trade.entry_role = "support" if trade.entry_risk_multiplier < 1.0 else "core"
        trade.entry_priority = 0 if trade.entry_role == "support" else 1
        return trade


class ExplorationEnabledConfig(DummyConfig):
    def get(self, *keys, default=None):
        if keys == ("strategy", "exploration"):
            return {
                "enabled": True,
                "enabled_sides": ["long", "short"],
                "allow_neutral_bias": True,
                "block_opposite_bias": True,
                "require_atr_rising": True,
                "require_vwap_alignment": False,
                "require_macd_alignment": False,
                "minimum_regime_score": 2,
                "allowed_regime_classes": ["strong", "moderate"],
                "pressure_score_threshold": 4,
                "entry_risk_multiplier": 0.25,
                "entry_priority": 0,
                "entry_role": "support",
            }
        return super().get(*keys, default=default)


class RecordingTrendSniffer:
    def __init__(self, result, calls):
        self.result = result
        self.calls = calls

    def is_trend_alive(self, row, trade=None):
        self.calls.append("trend")
        return self.result


class RecordingExitEngine:
    def __init__(self, result, calls):
        self.result = result
        self.calls = calls

    def should_exit(self, row, stop_price, side="long"):
        self.calls.append("hard_exit")
        return self.result


class RecordingPyramidingEngine:
    def __init__(self, next_level, calls):
        self.next_level = next_level
        self.calls = calls

    def qualifies_for_pyramiding(self, row, trade):
        self.calls.append("pyramid_quality")
        return True

    def check_pyramiding(self, **kwargs):
        self.calls.append("pyramid")
        return self.next_level

    def get_pyramid_size(self, base_size, level, quality_gate_passed=False):
        return 0.5

    def cap_add_size_by_risk(self, **kwargs):
        return kwargs["add_size"]


class DummyTrade:
    def __init__(self):
        self.side = "long"
        self.entry_price = 100.0
        self.stop = 95.0
        self.R = 5.0
        self.entry_risk_multiplier = 1.0
        self.entry_role = "core"
        self.entry_priority = 1
        self.intended_risk_per_trade = None
        self.pnl = 0.0
        self.closed = False
        self.added_entries = []
        self.exit_price = None
        self.exit_time = None

    def total_risk_to_stop(self):
        return 0.0

    def add_entry(self, price, size):
        self.added_entries.append((price, size))

    def close(self, row, exit_price=None):
        self.closed = True
        self.exit_time = row.name
        self.exit_price = row["close"] if exit_price is None else exit_price

    def annotate_risk_context(
        self,
        *,
        equity_at_entry=None,
        entry_risk_multiplier=None,
        intended_risk_per_trade=None,
        effective_risk_fraction=None,
    ):
        self.equity_at_entry = equity_at_entry
        self.entry_risk_multiplier = entry_risk_multiplier
        self.intended_risk_per_trade = intended_risk_per_trade
        self.effective_risk_fraction = effective_risk_fraction


class SimulatorManagementTests(unittest.TestCase):
    def _make_simulator(self, trend_ok, hard_exit, next_level=0):
        calls = []

        simulator = Simulator(
            initial_equity=1000.0,
            risk_per_trade=0.01,
            trade_logger=None,
            equity_logger=None,
            entry_engine=NullEntryEngine(),
            score_engine=StaticScoreEngine(),
            bias_detector=StaticBiasDetector(),
            regime_detector=StaticRegimeDetector(),
            pyramiding_engine=RecordingPyramidingEngine(next_level, calls),
            trend_sniffer=RecordingTrendSniffer(trend_ok, calls),
            exit_engine=RecordingExitEngine(hard_exit, calls),
            position_sizer=DummyPositionSizer(),
            config=DummyConfig(),
        )

        simulator.current_trade = DummyTrade()
        simulator.base_size = 1.0
        simulator.level = 0

        return simulator, calls

    def _make_row(self, close=101.0, low=None):
        return pd.Series(
            {"close": close, "low": close if low is None else low},
            name=pd.Timestamp("2026-01-01 00:00:00"),
        )

    def test_hard_exit_is_checked_before_trend_state_updates(self):
        simulator, calls = self._make_simulator(
            trend_ok=False,
            hard_exit=False,
        )

        row = self._make_row()
        empty_df = pd.DataFrame()

        simulator.step(row, empty_df, empty_df, empty_df)

        self.assertEqual(calls[:2], ["hard_exit", "trend"])
        self.assertIsNone(simulator.current_trade)

    def test_pyramiding_runs_only_after_trade_survives_exit_checks(self):
        simulator, calls = self._make_simulator(
            trend_ok=True,
            hard_exit=False,
            next_level=1,
        )

        row = self._make_row(close=110.0)
        empty_df = pd.DataFrame()

        simulator.step(row, empty_df, empty_df, empty_df)

        self.assertEqual(calls, ["hard_exit", "trend", "pyramid_quality", "pyramid"])
        self.assertIsNotNone(simulator.current_trade)
        self.assertEqual(simulator.level, 1)
        self.assertEqual(simulator.current_trade.added_entries, [(110.0, 0.5)])

    def test_hard_exit_prevents_pyramiding(self):
        simulator, calls = self._make_simulator(
            trend_ok=True,
            hard_exit=True,
            next_level=1,
        )

        trade = simulator.current_trade
        row = self._make_row(close=96.0, low=94.0)
        empty_df = pd.DataFrame()

        simulator.step(row, empty_df, empty_df, empty_df)

        self.assertEqual(calls, ["hard_exit"])
        self.assertIsNone(simulator.current_trade)
        self.assertEqual(trade.exit_price, trade.stop)

    def test_zero_position_size_skips_opening_dummy_trade(self):
        entry_engine = FixedEntryEngine()
        equity_logger = RecordingEquityLogger()
        simulator = Simulator(
            initial_equity=1000.0,
            risk_per_trade=0.01,
            trade_logger=None,
            equity_logger=equity_logger,
            entry_engine=entry_engine,
            score_engine=PositiveScoreEngine(),
            bias_detector=StaticBiasDetector(),
            regime_detector=StaticRegimeDetector(),
            pyramiding_engine=RecordingPyramidingEngine(0, []),
            trend_sniffer=RecordingTrendSniffer(True, []),
            exit_engine=RecordingExitEngine(False, []),
            position_sizer=ZeroPositionSizer(),
            config=DummyConfig(),
        )

        row = self._make_row(close=101.0)
        empty_df = pd.DataFrame()

        simulator.step(row, empty_df, empty_df, empty_df)

        self.assertIsNone(simulator.current_trade)
        self.assertEqual(simulator.base_size, 0)
        self.assertEqual(entry_engine.trade.added_entries, [])
        self.assertEqual(equity_logger.calls, [(row.name, 1000.0)])

    def test_weak_regime_blocks_entry_before_trade_generation(self):
        entry_engine = FixedEntryEngine()
        equity_logger = RecordingEquityLogger()
        simulator = Simulator(
            initial_equity=1000.0,
            risk_per_trade=0.01,
            trade_logger=None,
            equity_logger=equity_logger,
            entry_engine=entry_engine,
            score_engine=PositiveScoreEngine(),
            bias_detector=StaticBiasDetector(),
            regime_detector=BlockingRegimeDetector(),
            pyramiding_engine=RecordingPyramidingEngine(0, []),
            trend_sniffer=RecordingTrendSniffer(True, []),
            exit_engine=RecordingExitEngine(False, []),
            position_sizer=DummyPositionSizer(),
            config=DummyConfig(),
        )

        row = self._make_row(close=101.0)
        empty_df = pd.DataFrame()

        simulator.step(row, empty_df, empty_df, empty_df)

        self.assertIsNone(simulator.current_trade)
        self.assertEqual(entry_engine.calls, 0)
        self.assertEqual(equity_logger.calls, [(row.name, 1000.0)])

    def test_entry_trade_captures_forensic_context(self):
        entry_engine = FixedEntryEngine()
        simulator = Simulator(
            initial_equity=1000.0,
            risk_per_trade=0.01,
            trade_logger=None,
            equity_logger=None,
            entry_engine=entry_engine,
            score_engine=PositiveScoreEngine(),
            bias_detector=StaticBiasDetector(),
            regime_detector=ContextRegimeDetector(),
            pyramiding_engine=RecordingPyramidingEngine(0, []),
            trend_sniffer=RecordingTrendSniffer(True, []),
            exit_engine=RecordingExitEngine(False, []),
            position_sizer=DummyPositionSizer(),
            config=DummyConfig(),
        )

        row = self._make_row(close=101.0)
        empty_df = pd.DataFrame()

        simulator.step(row, empty_df, empty_df, empty_df)

        trade = simulator.current_trade
        self.assertIsNotNone(trade)
        self.assertEqual(trade.bias, "bullish")
        self.assertEqual(trade.regime_score, 3)
        self.assertEqual(trade.regime_class, "strong")
        self.assertEqual(trade.entry_threshold, 4)

    def test_directional_competition_can_open_short_trade(self):
        class ShortBiasDetector:
            def get_bias(self, df_1h):
                return "bearish"

        class ShortScoreEngine:
            def compute_score(self, row, bias, side="long"):
                return 2 if side == "long" else 6

        entry_engine = FixedEntryEngine()
        simulator = Simulator(
            initial_equity=1000.0,
            risk_per_trade=0.01,
            trade_logger=None,
            equity_logger=None,
            entry_engine=entry_engine,
            score_engine=ShortScoreEngine(),
            bias_detector=ShortBiasDetector(),
            regime_detector=ContextRegimeDetector(),
            pyramiding_engine=RecordingPyramidingEngine(0, []),
            trend_sniffer=RecordingTrendSniffer(True, []),
            exit_engine=RecordingExitEngine(False, []),
            position_sizer=DummyPositionSizer(),
            config=DummyConfig(),
        )

        row = self._make_row(close=99.0)
        empty_df = pd.DataFrame()

        simulator.step(row, empty_df, empty_df, empty_df)

        self.assertIsNotNone(simulator.current_trade)
        self.assertEqual(simulator.current_trade.side, "short")

    def test_short_entries_can_use_side_specific_risk_budget(self):
        class ShortBiasDetector:
            def get_bias(self, df_1h):
                return "bearish"

        class ShortScoreEngine:
            def compute_score(self, row, bias, side="long"):
                return 2 if side == "long" else 6

        position_sizer = RecordingPositionSizer()
        simulator = Simulator(
            initial_equity=1000.0,
            risk_per_trade=None,
            trade_logger=None,
            equity_logger=None,
            entry_engine=FixedEntryEngine(),
            score_engine=ShortScoreEngine(),
            bias_detector=ShortBiasDetector(),
            regime_detector=ContextRegimeDetector(),
            pyramiding_engine=RecordingPyramidingEngine(0, []),
            trend_sniffer=RecordingTrendSniffer(True, []),
            exit_engine=RecordingExitEngine(False, []),
            position_sizer=position_sizer,
            config=SideRiskConfig(),
        )

        row = self._make_row(close=99.0)
        empty_df = pd.DataFrame()

        simulator.step(row, empty_df, empty_df, empty_df)

        self.assertEqual(len(position_sizer.calls), 1)
        self.assertAlmostEqual(position_sizer.calls[0]["risk_per_trade"], 0.005)

    def test_support_alpha_entry_can_scale_down_long_risk_budget(self):
        position_sizer = RecordingPositionSizer()
        simulator = Simulator(
            initial_equity=1000.0,
            risk_per_trade=0.01,
            trade_logger=None,
            equity_logger=None,
            entry_engine=FixedEntryEngine(entry_risk_multiplier=0.5),
            score_engine=PositiveScoreEngine(),
            bias_detector=StaticBiasDetector(),
            regime_detector=ContextRegimeDetector(),
            pyramiding_engine=RecordingPyramidingEngine(0, []),
            trend_sniffer=RecordingTrendSniffer(True, []),
            exit_engine=RecordingExitEngine(False, []),
            position_sizer=position_sizer,
            config=DummyConfig(),
        )

        row = self._make_row(close=101.0)
        empty_df = pd.DataFrame()

        simulator.step(row, empty_df, empty_df, empty_df)

        self.assertEqual(len(position_sizer.calls), 1)
        self.assertAlmostEqual(position_sizer.calls[0]["risk_per_trade"], 0.005)
        self.assertAlmostEqual(simulator.current_trade.entry_risk_multiplier, 0.5)
        self.assertAlmostEqual(simulator.current_trade.intended_risk_per_trade, 0.005)

    def test_directional_selection_respects_side_specific_thresholds(self):
        simulator = Simulator(
            initial_equity=1000.0,
            risk_per_trade=0.01,
            trade_logger=None,
            equity_logger=None,
            entry_engine=ThresholdAwareEntryEngine(),
            score_engine=MixedThresholdScoreEngine(),
            bias_detector=StaticBiasDetector(),
            regime_detector=ContextRegimeDetector(),
            pyramiding_engine=RecordingPyramidingEngine(0, []),
            trend_sniffer=RecordingTrendSniffer(True, []),
            exit_engine=RecordingExitEngine(False, []),
            position_sizer=DummyPositionSizer(),
            config=ShortThresholdConfig(),
        )

        row = self._make_row(close=101.0)
        empty_df = pd.DataFrame()

        simulator.step(row, empty_df, empty_df, empty_df)

        self.assertIsNotNone(simulator.current_trade)
        self.assertEqual(simulator.current_trade.side, "long")

    def test_core_trade_can_override_open_support_trade(self):
        simulator = Simulator(
            initial_equity=1000.0,
            risk_per_trade=0.01,
            trade_logger=None,
            equity_logger=None,
            entry_engine=OverrideAwareEntryEngine(),
            score_engine=OverrideScoreEngine(),
            bias_detector=StaticBiasDetector(),
            regime_detector=ContextRegimeDetector(),
            pyramiding_engine=RecordingPyramidingEngine(0, []),
            trend_sniffer=RecordingTrendSniffer(True, []),
            exit_engine=RecordingExitEngine(False, []),
            position_sizer=DummyPositionSizer(),
            config=DummyConfig(),
        )

        support_trade = DummyTrade()
        support_trade.side = "long"
        support_trade.entry_risk_multiplier = 0.5
        support_trade.entry_role = "support"
        support_trade.entry_priority = 0
        simulator.current_trade = support_trade
        simulator.base_size = 1.0
        simulator.level = 0

        row = self._make_row(close=101.0)
        empty_df = pd.DataFrame()

        simulator.step(row, empty_df, empty_df, empty_df)

        self.assertTrue(support_trade.closed)
        self.assertEqual(support_trade.exit_reason, "core override")
        self.assertIsNotNone(simulator.current_trade)
        self.assertIsNot(simulator.current_trade, support_trade)
        self.assertEqual(simulator.current_trade.entry_role, "core")

    def test_exit_reason_is_attached_before_trade_is_closed(self):
        simulator, _calls = self._make_simulator(
            trend_ok=False,
            hard_exit=False,
        )

        trade = simulator.current_trade
        row = self._make_row()
        empty_df = pd.DataFrame()

        simulator.step(row, empty_df, empty_df, empty_df)

        self.assertEqual(trade.exit_reason, "trend weakness")

    def test_exploratory_candidate_can_open_when_core_threshold_is_not_met(self):
        class ExplorationScoreEngine:
            def compute_score(self, row, bias, side="long"):
                return 1

        entry_engine = ThresholdAwareEntryEngine()
        simulator = Simulator(
            initial_equity=1000.0,
            risk_per_trade=0.01,
            trade_logger=None,
            equity_logger=None,
            entry_engine=entry_engine,
            score_engine=ExplorationScoreEngine(),
            bias_detector=StaticBiasDetector(),
            regime_detector=ContextRegimeDetector(),
            pyramiding_engine=RecordingPyramidingEngine(0, []),
            trend_sniffer=RecordingTrendSniffer(True, []),
            exit_engine=RecordingExitEngine(False, []),
            position_sizer=DummyPositionSizer(),
            config=ExplorationEnabledConfig(),
        )

        row = self._make_row(close=101.0)
        row["pressure_score_long"] = 5
        row["pressure_ignition_long"] = True
        row["atr_rising"] = True
        row["ll2"] = 95.0
        empty_df = pd.DataFrame()

        simulator.step(row, empty_df, empty_df, empty_df)

        self.assertIsNotNone(simulator.current_trade)
        self.assertEqual(simulator.current_trade.signal_family, "exploratory")
        self.assertEqual(simulator.current_trade.entry_role, "support")


if __name__ == "__main__":
    unittest.main()
