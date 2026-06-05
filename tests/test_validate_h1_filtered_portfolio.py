import unittest

from backtest.validate_h1_filtered_portfolio import _normalize_symbols, _strategy_overrides


class ValidateH1FilteredPortfolioTests(unittest.TestCase):
    def test_normalize_symbols_uppercases_and_preserves_order(self):
        self.assertEqual(
            _normalize_symbols(["btcusdt", "EthUsdt"]),
            ["BTCUSDT", "ETHUSDT"],
        )

    def test_strategy_overrides_applies_symbol_and_side_filters(self):
        overrides = _strategy_overrides(["BTCUSDT", "ETHUSDT"], ["long", "short"])

        self.assertTrue(overrides["h1_execution"]["enabled"])
        self.assertEqual(overrides["h1_execution"]["allowed_symbols"], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(overrides["h1_execution"]["allowed_sides"], ["long", "short"])


if __name__ == "__main__":
    unittest.main()
