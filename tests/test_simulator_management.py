import unittest

import pandas as pd

from simulation.simulator import Simulator


class DummyConfig:
    def require(self, *keys):
        if keys == ("entry", "score_threshold"):
            return 4
        raise KeyError(f"Unexpected config lookup: {keys}")


class StaticBiasDetector:
    def get_bias(self, df_1h):
        return "bullish"


class StaticRegimeDetector:
    def compute_regime(self, df_5h, df_12h):
        return None


class ContextRegimeDetector:
    def compute_regime(self, df_5h, df_12h):
        return 3

    def classify(self, regime_score):
        return "strong"


class BlockingRegimeDetector:
    def compute_regime(self, df_5h, df_12h):
        return 1

    def allows_entries(self, regime_score):
        return False


class StaticScoreEngine:
    def compute_score(self, row, bias):
        return 0


class PositiveScoreEngine:
    def compute_score(self, row, bias):
        return 5


class NullEntryEngine:
    def generate_entry(self, row, score, bias):
        return None


class DummyPositionSizer:
    def calculate(self, **kwargs):
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
    def __init__(self):
        self.trade = DummyTrade()
        self.calls = 0

    def generate_entry(self, row, score, bias):
        self.calls += 1
        return self.trade


class RecordingTrendSniffer:
    def __init__(self, result, calls):
        self.result = result
        self.calls = calls

    def is_trend_alive(self, row):
        self.calls.append("trend")
        return self.result


class RecordingExitEngine:
    def __init__(self, result, calls):
        self.result = result
        self.calls = calls

    def should_exit(self, row, stop_price):
        self.calls.append("hard_exit")
        return self.result


class RecordingPyramidingEngine:
    def __init__(self, next_level, calls):
        self.next_level = next_level
        self.calls = calls

    def check_pyramiding(self, **kwargs):
        self.calls.append("pyramid")
        return self.next_level

    def get_pyramid_size(self, base_size, level):
        return 0.5

    def cap_add_size_by_risk(self, **kwargs):
        return kwargs["add_size"]


class DummyTrade:
    def __init__(self):
        self.entry_price = 100.0
        self.stop = 95.0
        self.R = 5.0
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

    def test_trend_is_evaluated_before_hard_exit(self):
        simulator, calls = self._make_simulator(
            trend_ok=False,
            hard_exit=False,
        )

        row = self._make_row()
        empty_df = pd.DataFrame()

        simulator.step(row, empty_df, empty_df, empty_df)

        self.assertEqual(calls[:2], ["trend", "hard_exit"])
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

        self.assertEqual(calls, ["trend", "hard_exit", "pyramid"])
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

        self.assertEqual(calls, ["trend", "hard_exit"])
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


if __name__ == "__main__":
    unittest.main()
