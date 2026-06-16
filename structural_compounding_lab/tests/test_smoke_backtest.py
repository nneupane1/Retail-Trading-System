import json
import tempfile
import unittest
from pathlib import Path

from structural_compounding_lab.backtest.engine import StructuralBacktestEngine
from structural_compounding_lab.config import StructuralLabConfig


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "btcusdt_structural_fixture_1m.csv"


class StructuralSmokeBacktestTests(unittest.TestCase):
    def test_engine_writes_artifact_bundle(self):
        self.assertTrue(FIXTURE.exists(), f"missing fixture csv: {FIXTURE}")
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "artifacts"
            config_path = Path(tmpdir) / "structural_test_settings.json"
            config_path.write_text(
                json.dumps(
                    {
                        "symbol": "BTCUSDT",
                        "execution_timeframe": "15m",
                        "confirmation_timeframes": ["1h", "4h"],
                        "visual_timeframes": ["15m", "1h", "4h"],
                        "base_capital": 20000,
                        "risk": {
                            "risk_per_trade_pct": 0.01,
                            "max_concurrent_positions": 1,
                            "max_hold_bars": 24,
                            "minimum_rr": 1.05,
                        },
                        "ema": {"fast": 3, "mid": 5, "slow": 8},
                        "atr": {"period": 3, "shock_multiple": 2.0},
                        "sr": {
                            "pivot_left": 1,
                            "pivot_right": 1,
                            "touch_tolerance_pct": 0.003,
                            "rolling_range_bars": 12,
                            "zone_width_pct": 0.002,
                        },
                        "liquidity": {
                            "equal_level_tolerance_pct": 0.002,
                            "sweep_lookback_bars": 6,
                            "reclaim_tolerance_pct": 0.001,
                        },
                        "pyramiding": {
                            "enabled": True,
                            "max_add_ons": 1,
                            "add_on_trigger_r": 0.8,
                            "size_fraction": 0.2,
                        },
                        "cooldown": {"enabled": True, "bars": 2, "requires_danger_clear": False},
                        "profit_vault": {
                            "enabled": True,
                            "lock_on_danger": True,
                            "reset_active_capital_to_base": True,
                            "minimum_lock_profit": 0.0,
                        },
                    }
                ),
                encoding="utf-8",
            )

            config = StructuralLabConfig.load(config_path)
            engine = StructuralBacktestEngine(config=config)
            summary = engine.run(symbol="BTCUSDT", source_csv=FIXTURE, output_dir=output_dir)

            self.assertEqual(summary["symbol"], "BTCUSDT")
            self.assertIn("metrics", summary)
            self.assertIn("profit_lock_count", summary)
            self.assertIn("add_on_event_count", summary)
            self.assertIn("cooldown_event_count", summary)
            self.assertIn("run_context", summary)
            self.assertEqual(summary["run_context"]["structure_window_bars"], 240)
            self.assertEqual(summary["run_state"], "completed")
            self.assertTrue((output_dir / "summary.json").exists())
            self.assertTrue((output_dir / "equity.csv").exists())
            self.assertTrue((output_dir / "setup_log.csv").exists())
            self.assertTrue((output_dir / "level_log.csv").exists())
            self.assertTrue((output_dir / "liquidity_events.csv").exists())
            self.assertTrue((output_dir / "profit_vault.json").exists())
            self.assertTrue((output_dir / "report.md").exists())
            self.assertTrue((output_dir / "status.json").exists())
            self.assertTrue((output_dir / "scenario_progress.json").exists())

            setup_rows = (output_dir / "setup_log.csv").read_text(encoding="utf-8")
            self.assertIn("decision", setup_rows)
            self.assertIn("opened", setup_rows)


if __name__ == "__main__":
    unittest.main()
