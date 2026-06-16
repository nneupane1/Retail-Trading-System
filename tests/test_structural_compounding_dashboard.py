import json
import tempfile
import unittest
from pathlib import Path

from common.dashboard_telemetry import load_structural_lab_snapshot


class StructuralCompoundingDashboardTests(unittest.TestCase):
    def test_snapshot_returns_honest_empty_state_without_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "structural_compounding_lab" / "config").mkdir(parents=True, exist_ok=True)
            (root / "structural_compounding_lab" / "config" / "structural_compounding_settings.json").write_text(
                json.dumps({"base_capital": 20000, "visual_timeframes": ["1h", "12h"]}),
                encoding="utf-8",
            )
            (root / "structural_compounding_lab" / "config" / "symbols.json").write_text(
                json.dumps({"symbols": ["BTCUSDT"]}),
                encoding="utf-8",
            )

            snapshot = load_structural_lab_snapshot(root_dir=root)

            self.assertFalse(snapshot["lab"]["has_run"])
            self.assertEqual(snapshot["lab"]["empty_state"], "No structural backtest run found yet.")
            self.assertIn("No structural backtest run found yet.", snapshot["warnings"])
            self.assertIn("BTCUSDT", snapshot["available_symbols"])

    def test_snapshot_reads_structural_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_root = root / "structural_compounding_lab" / "config"
            output_root = root / "structural_compounding_lab" / "output"
            config_root.mkdir(parents=True, exist_ok=True)
            output_root.mkdir(parents=True, exist_ok=True)

            (config_root / "structural_compounding_settings.json").write_text(
                json.dumps({"base_capital": 20000, "visual_timeframes": ["1h", "4h", "12h"]}),
                encoding="utf-8",
            )
            (config_root / "symbols.json").write_text(
                json.dumps({"symbols": ["BTCUSDT", "ETHUSDT"]}),
                encoding="utf-8",
            )
            (output_root / "summary.json").write_text(
                json.dumps(
                    {
                        "current_equity": 24500,
                        "locked_profit": 3000,
                        "active_trading_capital": 20000,
                        "cooldown_active": False,
                        "current_compounding_cycle": "cycle-3",
                        "metrics": {
                            "total_return_pct": 0.225,
                            "max_drawdown_pct": 0.08,
                            "win_rate": 0.56,
                            "profit_factor": 1.34,
                            "r_multiple_summary": "1R and 2R winners dominate while moonshots remain rare."
                        }
                    }
                ),
                encoding="utf-8",
            )
            (output_root / "profit_vault.json").write_text(
                json.dumps(
                    {
                        "base_capital": 20000,
                        "active_trading_capital": 20000,
                        "locked_profit": 3000,
                        "floating_profit": 1500,
                        "current_compounding_cycle_id": "cycle-3"
                    }
                ),
                encoding="utf-8",
            )
            (output_root / "trades.csv").write_text(
                "symbol,side,pnl,entry_reason,exit_reason\nBTCUSDT,long,250,sweep reclaim,trail exit\n",
                encoding="utf-8",
            )
            diagnostics_root = output_root / "diagnostics"
            reports_root = output_root / "reports"
            diagnostics_root.mkdir(parents=True, exist_ok=True)
            reports_root.mkdir(parents=True, exist_ok=True)
            (diagnostics_root / "pullback_quality_report.json").write_text(
                json.dumps({"count": 1, "average_improved_R_delta": 1.2}),
                encoding="utf-8",
            )
            (reports_root / "promotion_packet.json").write_text(
                json.dumps({"requires_manual_promotion": True}),
                encoding="utf-8",
            )
            (output_root / "equity.csv").write_text(
                "timestamp,equity\n2026-01-01T00:00:00+00:00,20000\n2026-01-02T00:00:00+00:00,24500\n",
                encoding="utf-8",
            )

            snapshot = load_structural_lab_snapshot(root_dir=root)

            self.assertTrue(snapshot["lab"]["has_run"])
            self.assertEqual(snapshot["overview"]["current_compounding_cycle"], "cycle-3")
            self.assertEqual(snapshot["overview"]["locked_profit"], 3000)
            self.assertEqual(snapshot["overview"]["active_trading_capital"], 20000)
            self.assertEqual(len(snapshot["trade_rows"]), 1)
            self.assertTrue(snapshot["artifact_freshness"]["summary"]["exists"])
            self.assertEqual(1, snapshot["research_reports"]["pullback_quality_report"]["count"])


if __name__ == "__main__":
    unittest.main()
