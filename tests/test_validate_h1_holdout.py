import unittest

import pandas as pd

from backtest.validate_h1_holdout import _classify_training_symbols


class ValidateH1HoldoutTests(unittest.TestCase):
    def test_classify_training_symbols_marks_keep_when_symbol_is_positive_and_active(self):
        summary_df = pd.DataFrame(
            [
                {
                    "symbol": "BNBUSDT",
                    "trade_count": 80,
                    "net_R": 10.0,
                    "avg_R": 0.125,
                    "median_R": 0.05,
                    "max_R": 2.5,
                    "win_rate": 0.5,
                    "hit_1R_rate": 0.45,
                    "hit_2R_rate": 0.20,
                },
                {
                    "symbol": "BTCUSDT",
                    "trade_count": 80,
                    "net_R": -2.0,
                    "avg_R": -0.025,
                    "median_R": -0.10,
                    "max_R": 1.0,
                    "win_rate": 0.4,
                    "hit_1R_rate": 0.30,
                    "hit_2R_rate": 0.10,
                },
            ]
        )
        events_df = pd.DataFrame(
            [
                {"symbol": "BNBUSDT", "realized_R": 6.0},
                {"symbol": "BNBUSDT", "realized_R": 4.0},
                {"symbol": "BTCUSDT", "realized_R": -1.0},
                {"symbol": "BTCUSDT", "realized_R": -1.0},
            ]
        )

        rows = _classify_training_symbols(summary_df, events_df)
        by_symbol = {row["symbol"]: row for row in rows}
        self.assertEqual("keep", by_symbol["BNBUSDT"]["status"])
        self.assertEqual("drop", by_symbol["BTCUSDT"]["status"])


if __name__ == "__main__":
    unittest.main()
