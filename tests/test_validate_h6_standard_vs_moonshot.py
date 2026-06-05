import json
import tempfile
import unittest
from pathlib import Path

from backtest.validate_h6_standard_vs_moonshot import _engine_config, _load_keep_symbols
from config import AppConfig


class ValidateH6StandardVsMoonshotTests(unittest.TestCase):
    def test_load_keep_symbols_reads_holdout_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "backtest_output"
            holdout_dir = output_dir / "h6_moonshot_holdout_current"
            holdout_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "training_symbol_curation": {
                    "keep_symbols": ["BNBUSDT", "TRXUSDT"],
                }
            }
            (holdout_dir / "summary.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            config = AppConfig(
                data={"backtest": {"output_dir": str(output_dir)}},
                config_path=Path(tmpdir) / "settings.json",
                root_dir=Path(tmpdir),
            )

            keep_symbols = _load_keep_symbols(config)

            self.assertEqual(["BNBUSDT", "TRXUSDT"], keep_symbols)

    def test_engine_config_enables_only_requested_engine(self):
        config = AppConfig(
            data={
                "strategy": {
                    "h6_moonshot": {"enabled": False},
                    "h6_standard": {"enabled": False},
                }
            },
            config_path=Path("settings.json"),
            root_dir=Path("."),
        )

        moonshot_config = _engine_config(config, "h6_moonshot")
        standard_config = _engine_config(config, "h6_standard")

        self.assertTrue(moonshot_config.data["strategy"]["h6_moonshot"]["enabled"])
        self.assertFalse(moonshot_config.data["strategy"]["h6_standard"]["enabled"])
        self.assertFalse(standard_config.data["strategy"]["h6_moonshot"]["enabled"])
        self.assertTrue(standard_config.data["strategy"]["h6_standard"]["enabled"])


if __name__ == "__main__":
    unittest.main()
