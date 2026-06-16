import json
import tempfile
import unittest
from pathlib import Path

from structural_compounding_lab.backtest.engine import StructuralBacktestEngine
from structural_compounding_lab.config import StructuralLabConfig


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "btcusdt_structural_fixture_1m.csv"


class StructuralCheckpointResumeTests(unittest.TestCase):
    def test_engine_can_checkpoint_and_resume(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "artifacts"
            config_path = Path(tmpdir) / "checkpoint_settings.json"
            config_path.write_text(
                json.dumps(
                    {
                        "symbol": "BTCUSDT",
                        "execution_timeframe": "15m",
                        "confirmation_timeframes": ["1h", "4h"],
                        "visual_timeframes": ["15m", "1h", "4h"],
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
                        "engine": {
                            "structure_window_bars": 64,
                            "liquidity_window_bars": 48,
                            "setup_window_bars": 32,
                            "resume_enabled": True,
                            "checkpoint_every_bars": 4,
                            "write_partial_artifacts": True,
                        },
                    }
                ),
                encoding="utf-8",
            )

            config = StructuralLabConfig.load(config_path)
            engine = StructuralBacktestEngine(config=config)

            partial = engine.run(
                symbol="BTCUSDT",
                source_csv=FIXTURE,
                output_dir=output_dir,
                max_bars=6,
            )
            self.assertEqual(partial["run_state"], "interrupted")
            self.assertTrue((output_dir / "_checkpoints" / "structural_backtest.checkpoint.json").exists())
            self.assertTrue((output_dir / "summary.json").exists())

            resumed = engine.run(
                symbol="BTCUSDT",
                source_csv=FIXTURE,
                output_dir=output_dir,
            )
            self.assertEqual(resumed["run_state"], "completed")
            self.assertTrue(resumed["resumed_from_checkpoint"])
            self.assertTrue((output_dir / "trades.csv").exists())
            self.assertTrue((output_dir / "status.json").exists())
            self.assertTrue((output_dir / "scenario_progress.json").exists())


if __name__ == "__main__":
    unittest.main()
