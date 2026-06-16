import json
import tempfile
import unittest
from pathlib import Path

from structural_compounding_lab.config import StructuralLabConfig


class StructuralConfigLoadingTests(unittest.TestCase):
    def test_loader_normalizes_legacy_schema(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "legacy.json"
            config_path.write_text(
                json.dumps(
                    {
                        "research_only": True,
                        "primary_execution_timeframe": "15m",
                        "indicators": {
                            "ema_fast": 8,
                            "ema_mid": 21,
                            "ema_slow": 55,
                            "atr_period": 10,
                        },
                        "cooldown": {"minimum_bars": 4},
                        "data": {
                            "run_start_date": "2026-01-01",
                            "run_end_date": "2026-01-31",
                        },
                    }
                ),
                encoding="utf-8",
            )

            config = StructuralLabConfig.load(config_path)

            self.assertEqual(config.require("execution_timeframe"), "15m")
            self.assertEqual(config.require("ema", "fast"), 8)
            self.assertEqual(config.require("ema", "mid"), 21)
            self.assertEqual(config.require("ema", "slow"), 55)
            self.assertEqual(config.require("atr", "period"), 10)
            self.assertEqual(config.require("cooldown", "bars"), 4)
            self.assertEqual(config.get("data", "analysis_start_date"), "2026-01-01")
            self.assertEqual(config.get("data", "analysis_end_date"), "2026-01-31")


if __name__ == "__main__":
    unittest.main()
