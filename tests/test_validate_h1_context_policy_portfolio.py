import unittest

from backtest.validate_h1_context_policy_portfolio import _context_strategy_overrides


class ValidateH1ContextPolicyPortfolioTests(unittest.TestCase):
    def test_context_strategy_overrides_embed_htf_context_side_policy(self):
        overrides = _context_strategy_overrides(["BTCUSDT", "ETHUSDT"])

        self.assertTrue(overrides["h1_execution"]["enabled"])
        self.assertEqual(overrides["h1_execution"]["allowed_symbols"], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(overrides["h1_execution"]["allowed_sides"], ["long", "short"])
        policy = overrides["h1_execution"]["context_side_policy"]
        self.assertEqual(policy["bearish"]["allowed_sides"], ["short"])
        self.assertEqual(policy["neutral"]["short_selection_threshold_offset"], -0.03)
        self.assertEqual(policy["bullish"]["long_selection_threshold_offset"], -0.03)
        self.assertEqual(policy["bullish"]["short_risk_multiplier"], 0.9)


if __name__ == "__main__":
    unittest.main()
