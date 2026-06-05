import unittest
from pathlib import Path

from backtest.validate_h6_standard_holdout import _research_config
from config import AppConfig


class ValidateH6StandardHoldoutTests(unittest.TestCase):
    def test_research_config_clears_symbol_filters_and_enables_engine(self):
        base = AppConfig(
            data={
                "strategy": {
                    "h6_standard": {
                        "enabled": False,
                        "allowed_symbols": ["ETHUSDT"],
                        "blocked_symbols": ["BTCUSDT"],
                    }
                }
            },
            config_path=Path("settings.json"),
            root_dir=Path("."),
        )

        config = _research_config(base)

        self.assertTrue(config.data["strategy"]["h6_standard"]["enabled"])
        self.assertEqual([], config.data["strategy"]["h6_standard"]["allowed_symbols"])
        self.assertEqual([], config.data["strategy"]["h6_standard"]["blocked_symbols"])


if __name__ == "__main__":
    unittest.main()
