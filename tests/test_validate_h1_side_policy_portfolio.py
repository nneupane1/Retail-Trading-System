import unittest

from backtest.validate_h1_side_policy_portfolio import _strategy_overrides


class ValidateH1SidePolicyPortfolioTests(unittest.TestCase):
    def test_strategy_overrides_apply_side_policy_fields(self):
        overrides = _strategy_overrides(
            allowed_symbols=["BTCUSDT", "ETHUSDT"],
            allowed_sides=["short"],
            long_selection_threshold_offset=0.01,
            short_selection_threshold_offset=-0.04,
            long_risk_multiplier=0.9,
            short_risk_multiplier=1.1,
        )

        self.assertTrue(overrides["h1_execution"]["enabled"])
        self.assertEqual(overrides["h1_execution"]["allowed_symbols"], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(overrides["h1_execution"]["allowed_sides"], ["short"])
        self.assertEqual(overrides["h1_execution"]["long_selection_threshold_offset"], 0.01)
        self.assertEqual(overrides["h1_execution"]["short_selection_threshold_offset"], -0.04)
        self.assertEqual(overrides["h1_execution"]["long_risk_multiplier"], 0.9)
        self.assertEqual(overrides["h1_execution"]["short_risk_multiplier"], 1.1)


if __name__ == "__main__":
    unittest.main()
