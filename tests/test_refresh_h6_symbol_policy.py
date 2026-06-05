import json
import tempfile
import unittest
from pathlib import Path

from backtest.refresh_h6_symbol_policy import _comparison_summary, _moonshot_keep_symbols
from config import AppConfig


class RefreshH6SymbolPolicyTests(unittest.TestCase):
    def test_loaders_read_expected_validation_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "backtest_output"
            holdout_dir = output_dir / "h6_moonshot_holdout_current"
            comparison_dir = output_dir / "h6_standard_vs_moonshot_current"
            holdout_dir.mkdir(parents=True, exist_ok=True)
            comparison_dir.mkdir(parents=True, exist_ok=True)

            (holdout_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "training_symbol_curation": {
                            "keep_symbols": ["BNBUSDT", "TRXUSDT"],
                        }
                    }
                ),
                encoding="utf-8",
            )
            (comparison_dir / "summary.json").write_text(
                json.dumps({"engines": {"h6_standard": {"holdout_metrics": {"trade_count": 1}}}}),
                encoding="utf-8",
            )

            config = AppConfig(
                data={"backtest": {"output_dir": str(output_dir)}},
                config_path=Path(tmpdir) / "settings.json",
                root_dir=Path(tmpdir),
            )

            self.assertEqual(["BNBUSDT", "TRXUSDT"], _moonshot_keep_symbols(config))
            self.assertEqual(1, _comparison_summary(config)["engines"]["h6_standard"]["holdout_metrics"]["trade_count"])


if __name__ == "__main__":
    unittest.main()
