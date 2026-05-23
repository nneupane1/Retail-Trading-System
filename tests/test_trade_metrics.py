import unittest

import pandas as pd

from simulation.trade import Trade


class DummyConfig:
    def __init__(self, low_period=2, high_period=2):
        self.low_period = low_period
        self.high_period = high_period

    def require(self, *keys):
        if keys == ("features", "structure", "low_period"):
            return self.low_period
        if keys == ("features", "structure", "high_period"):
            return self.high_period
        raise KeyError(f"Unexpected config lookup: {keys}")


class TradeMetricsTests(unittest.TestCase):
    def test_trade_tracks_total_and_initial_r_multiples(self):
        entry_row = pd.Series(
            {
                "close": 100.0,
                "ll2": 95.0,
                "body_strength": 1.5,
                "close_position": 0.8,
                "upper_wick_ratio": 0.3,
                "compression": True,
                "breakout": True,
            },
            name=pd.Timestamp("2026-01-01 00:00:00"),
        )
        exit_row = pd.Series(
            {
                "close": 110.0,
            },
            name=pd.Timestamp("2026-01-01 01:00:00"),
        )

        trade = Trade(entry_row, score=5, config=DummyConfig())
        trade.annotate_entry_context(
            bias="bullish",
            regime_score=3,
            regime_class="strong",
            entry_threshold=4,
        )
        trade.add_entry(100.0, 1.0)
        trade.add_entry(105.0, 0.5)
        trade.pyramid_level = 1
        trade.annotate_exit(reason="trend weakness")
        trade.close(exit_row)

        self.assertEqual(trade.initial_risk_amount, 5.0)
        self.assertEqual(trade.total_risk_amount, 10.0)
        self.assertEqual(trade.pnl, 12.5)
        self.assertEqual(trade.pnl_R, 1.25)
        self.assertEqual(trade.pnl_R_total, 1.25)
        self.assertEqual(trade.pnl_R_initial, 2.5)
        self.assertEqual(trade.bias, "bullish")
        self.assertEqual(trade.regime_score, 3)
        self.assertEqual(trade.regime_class, "strong")
        self.assertEqual(trade.entry_threshold, 4)
        self.assertEqual(trade.exit_reason, "trend weakness")
        self.assertEqual(trade.pyramid_level, 1)

    def test_trade_can_close_at_explicit_execution_price(self):
        entry_row = pd.Series(
            {
                "close": 100.0,
                "ll2": 95.0,
                "body_strength": 1.5,
                "close_position": 0.8,
                "upper_wick_ratio": 0.3,
                "compression": True,
                "breakout": True,
            },
            name=pd.Timestamp("2026-01-01 00:00:00"),
        )
        exit_row = pd.Series(
            {
                "close": 92.0,
            },
            name=pd.Timestamp("2026-01-01 01:00:00"),
        )

        trade = Trade(entry_row, score=5, config=DummyConfig())
        trade.add_entry(100.0, 1.0)
        trade.annotate_exit(reason="hard exit")
        trade.close(exit_row, exit_price=95.0)

        self.assertEqual(trade.exit_price, 95.0)
        self.assertEqual(trade.pnl, -5.0)
        self.assertEqual(trade.pnl_R_initial, -1.0)

    def test_short_trade_pnl_uses_inverse_price_move(self):
        entry_row = pd.Series(
            {
                "close": 100.0,
                "hh2": 105.0,
                "body_strength": 1.5,
                "close_position": 0.2,
                "upper_wick_ratio": 0.3,
                "lower_wick_ratio": 0.2,
                "compression": False,
                "breakdown": True,
            },
            name=pd.Timestamp("2026-01-01 00:00:00"),
        )
        exit_row = pd.Series(
            {
                "close": 92.0,
            },
            name=pd.Timestamp("2026-01-01 01:00:00"),
        )

        trade = Trade(entry_row, score=6, side="short", config=DummyConfig())
        trade.add_entry(100.0, 1.0)
        trade.close(exit_row)

        self.assertEqual(trade.side, "short")
        self.assertEqual(trade.stop, 105.0)
        self.assertEqual(trade.pnl, 8.0)
        self.assertEqual(trade.pnl_R_initial, 1.6)


if __name__ == "__main__":
    unittest.main()
