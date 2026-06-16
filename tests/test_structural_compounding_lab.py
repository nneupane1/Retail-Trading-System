import json
import tempfile
import unittest
from pathlib import Path

from common.dashboard_telemetry import load_structural_lab_snapshot
from config import AppConfig
from structural_compounding_lab.backtest.engine import StructuralBacktestEngine
from structural_compounding_lab.config import StructuralLabConfig, load_candidate_registry


FIXTURE = Path(__file__).resolve().parents[1] / "structural_compounding_lab" / "tests" / "fixtures" / "btcusdt_structural_fixture_1m.csv"


class StructuralCompoundingLabProjectTests(unittest.TestCase):
    def test_registry_defaults_to_backtest_only(self):
        registry = load_candidate_registry()
        self.assertTrue(registry["research_only"])
        for candidate in registry["candidates"]:
            self.assertFalse(candidate["live_allowed"])
            self.assertFalse(candidate["paper_allowed"])
            self.assertFalse(candidate["real_money_allowed"])
            self.assertFalse(candidate["authoritative"])

    def test_validation_ladder_never_auto_runs_expensive_stages(self):
        ladder_path = Path(__file__).resolve().parents[1] / "structural_compounding_lab" / "config" / "validation_ladder.json"
        ladder = json.loads(ladder_path.read_text(encoding="utf-8"))
        stage_map = {stage["stage"]: stage for stage in ladder["stages"]}
        self.assertFalse(stage_map["full_history_confirmation"]["auto_run"])
        self.assertFalse(stage_map["monte_carlo"]["auto_run"])
        self.assertFalse(stage_map["paper_candidate_later"]["auto_run"])

    def test_structural_snapshot_surfaces_research_reports(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_root = root / "structural_compounding_lab" / "config"
            output_root = root / "structural_compounding_lab" / "output"
            diagnostics_root = output_root / "diagnostics"
            reports_root = output_root / "reports"
            config_root.mkdir(parents=True, exist_ok=True)
            diagnostics_root.mkdir(parents=True, exist_ok=True)
            reports_root.mkdir(parents=True, exist_ok=True)

            (config_root / "structural_compounding_settings.json").write_text(json.dumps({"base_capital": 20000, "visual_timeframes": ["1h", "4h", "12h"]}), encoding="utf-8")
            (config_root / "symbols.json").write_text(json.dumps({"symbols": ["BTCUSDT"]}), encoding="utf-8")
            (output_root / "summary.json").write_text(json.dumps({"current_equity": 21000, "metrics": {"profit_factor": 1.2}}), encoding="utf-8")
            (output_root / "profit_vault.json").write_text(json.dumps({"base_capital": 20000, "active_trading_capital": 20500, "locked_profit": 500}), encoding="utf-8")
            (output_root / "trades.csv").write_text("symbol,side,pnl\nBTCUSDT,long,100\n", encoding="utf-8")
            (diagnostics_root / "pullback_quality_report.json").write_text(json.dumps({"count": 2}), encoding="utf-8")
            (diagnostics_root / "personality_performance_report.json").write_text(json.dumps({"MOMENTUM_BURST": {"count": 1}}), encoding="utf-8")
            (reports_root / "promotion_packet.json").write_text(json.dumps({"requires_manual_promotion": True}), encoding="utf-8")

            snapshot = load_structural_lab_snapshot(root_dir=root)
            self.assertIn("research_reports", snapshot)
            self.assertEqual(2, snapshot["research_reports"]["pullback_quality_report"]["count"])
            self.assertTrue(snapshot["artifact_freshness"]["pullback_quality_report"]["exists"])

    def test_h1_override_and_6h_guard_remain_in_runtime_config(self):
        cfg = AppConfig.load()
        self.assertFalse(bool(cfg.require("strategy", "h6_standard", "enabled")))
        self.assertFalse(bool(cfg.require("strategy", "h6_moonshot", "enabled")))

    def test_engine_stays_research_only_and_writes_cost_reports(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "artifacts"
            config_path = Path(tmpdir) / "settings.json"
            config_path.write_text(
                json.dumps(
                    {
                        "symbol": "BTCUSDT",
                        "execution_timeframe": "15m",
                        "confirmation_timeframes": ["1h", "4h"],
                        "visual_timeframes": ["15m", "1h", "4h"],
                        "base_capital": 20000,
                        "risk": {"risk_per_trade_pct": 0.01, "max_concurrent_positions": 1, "max_hold_bars": 24, "minimum_rr": 1.05},
                        "ema": {"fast": 3, "mid": 5, "slow": 8},
                        "atr": {"period": 3, "shock_multiple": 2.0},
                        "sr": {"pivot_left": 1, "pivot_right": 1, "touch_tolerance_pct": 0.003, "rolling_range_bars": 12, "zone_width_pct": 0.002},
                        "liquidity": {"equal_level_tolerance_pct": 0.002, "sweep_lookback_bars": 6, "reclaim_tolerance_pct": 0.001},
                        "pyramiding": {"enabled": True, "max_add_ons": 1, "add_on_trigger_r": 0.8, "size_fraction": 0.2},
                        "cooldown": {"enabled": True, "bars": 2, "requires_danger_clear": False},
                        "profit_vault": {"enabled": True, "lock_on_danger": True, "reset_active_capital_to_base": True, "minimum_lock_profit": 0.0}
                    }
                ),
                encoding="utf-8",
            )
            config = StructuralLabConfig.load(config_path)
            engine = StructuralBacktestEngine(config=config)
            summary = engine.run(symbol="BTCUSDT", source_csv=FIXTURE, output_dir=output_dir)
            self.assertFalse(summary["research_diagnostics"]["candidate_registry"]["authoritative"])
            self.assertTrue((output_dir / "execution_realism" / "execution_cost_model.json").exists())
            self.assertTrue((output_dir / "diagnostics" / "pullback_compounding_readiness_report.json").exists())


if __name__ == "__main__":
    unittest.main()
