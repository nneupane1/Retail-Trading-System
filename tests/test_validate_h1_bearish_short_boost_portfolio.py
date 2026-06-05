import unittest

from backtest.validate_h1_bearish_short_boost_portfolio import (
    _bearish_short_boost_strategy_overrides,
)


class ValidateH1BearishShortBoostPortfolioTests(unittest.TestCase):
    def test_bearish_short_boost_strategy_overrides_only_changes_bearish_short_aggression(self):
        overrides = _bearish_short_boost_strategy_overrides(["BTCUSDT", "ETHUSDT"])

        h1 = overrides["h1_execution"]
        self.assertTrue(h1["enabled"])
        self.assertEqual(h1["allowed_symbols"], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(h1["allowed_sides"], ["short"])
        self.assertEqual(h1["short_selection_threshold_offset"], -0.04)
        self.assertEqual(h1["short_risk_multiplier"], 1.10)
        self.assertFalse(h1["elite_long_exception"]["enabled"])
        policy = h1["context_side_policy"]
        self.assertEqual(policy["bearish"]["short_selection_threshold_offset"], -0.06)
        self.assertEqual(policy["bearish"]["short_risk_multiplier"], 1.20)
        self.assertEqual(policy["neutral"]["short_selection_threshold_offset"], -0.04)
        self.assertEqual(policy["bullish"]["short_risk_multiplier"], 1.10)


if __name__ == "__main__":
    unittest.main()
