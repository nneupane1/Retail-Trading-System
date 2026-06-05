import unittest

from backtest.validate_h1_elite_long_portfolio import _elite_long_strategy_overrides


class ValidateH1EliteLongPortfolioTests(unittest.TestCase):
    def test_elite_long_strategy_overrides_keep_short_only_base_and_enable_exception(self):
        overrides = _elite_long_strategy_overrides(["BTCUSDT", "ETHUSDT"])

        h1 = overrides["h1_execution"]
        self.assertTrue(h1["enabled"])
        self.assertEqual(h1["allowed_symbols"], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(h1["allowed_sides"], ["short"])
        self.assertEqual(h1["short_selection_threshold_offset"], -0.04)
        self.assertEqual(h1["short_risk_multiplier"], 1.10)
        exception = h1["elite_long_exception"]
        self.assertTrue(exception["enabled"])
        self.assertEqual(exception["min_score"], 0.92)
        self.assertEqual(exception["risk_multiplier"], 0.80)


if __name__ == "__main__":
    unittest.main()
