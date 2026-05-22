import unittest

import pandas as pd

from simulation.trade import Trade


class DummyConfig:
    def __init__(self, low_period=2):
        self.low_period = low_period

    def require(self, *keys):
        if keys == ("features", "structure", "low_period"):
            return self.low_period
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
        trade.add_entry(100.0, 1.0)
        trade.add_entry(105.0, 0.5)
        trade.close(exit_row)

        self.assertEqual(trade.initial_risk_amount, 5.0)
        self.assertEqual(trade.total_risk_amount, 10.0)
        self.assertEqual(trade.pnl, 12.5)
        self.assertEqual(trade.pnl_R, 1.25)
        self.assertEqual(trade.pnl_R_total, 1.25)
        self.assertEqual(trade.pnl_R_initial, 2.5)


if __name__ == "__main__":
    unittest.main()
