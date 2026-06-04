import unittest

from backtest.validate_curated_holdout import _symbol_union


class ValidateCuratedHoldoutTests(unittest.TestCase):
    def test_symbol_union_appends_only_new_symbols(self):
        result = _symbol_union(
            ["BTCUSDT", "ETHUSDT"],
            ["ETHUSDT", "DOTUSDT", "FILUSDT"],
        )
        self.assertEqual(["BTCUSDT", "ETHUSDT", "DOTUSDT", "FILUSDT"], result)


if __name__ == "__main__":
    unittest.main()
