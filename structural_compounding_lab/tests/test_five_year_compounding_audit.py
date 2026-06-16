import csv
import json
import tempfile
import unittest
from pathlib import Path

from structural_compounding_lab.diagnostics.five_year_compounding_audit import (
    FiveYearCompoundingAuditConfig,
    write_five_year_compounding_audit,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


class FiveYearCompoundingAuditTests(unittest.TestCase):
    def test_full_active_capital_long_short_audit_outputs_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / "structural_compounding_lab"
            output_root = package_root / "output"
            output_root.mkdir(parents=True, exist_ok=True)

            (output_root / "summary.json").write_text(
                json.dumps({"current_equity": 24500.0, "ending_equity": 24500.0}),
                encoding="utf-8",
            )
            _write_csv(
                output_root / "trades.csv",
                [
                    {
                        "trade_id": "t1",
                        "symbol": "BTCUSDT",
                        "side": "long",
                        "entry_time": "2026-01-01T00:00:00+00:00",
                        "exit_time": "2026-01-01T02:00:00+00:00",
                        "pnl": 400.0,
                        "r_multiple": 2.0,
                    },
                    {
                        "trade_id": "t2",
                        "symbol": "BTCUSDT",
                        "side": "short",
                        "entry_time": "2026-01-02T00:00:00+00:00",
                        "exit_time": "2026-01-02T03:00:00+00:00",
                        "pnl": -204.0,
                        "r_multiple": -1.0,
                    },
                    {
                        "trade_id": "t3",
                        "symbol": "BTCUSDT",
                        "side": "short",
                        "entry_time": "2026-02-01T00:00:00+00:00",
                        "exit_time": "2026-02-01T04:00:00+00:00",
                        "pnl": 1224.0,
                        "r_multiple": 6.0,
                    },
                    {
                        "trade_id": "t4",
                        "symbol": "BTCUSDT",
                        "side": "long",
                        "entry_time": "2026-02-03T00:00:00+00:00",
                        "exit_time": "2026-02-03T04:00:00+00:00",
                        "pnl": -214.2,
                        "r_multiple": -1.0,
                    },
                    {
                        "trade_id": "t5",
                        "symbol": "BTCUSDT",
                        "side": "short",
                        "entry_time": "2026-03-01T00:00:00+00:00",
                        "exit_time": "2026-03-01T06:00:00+00:00",
                        "pnl": 2142.0,
                        "r_multiple": 10.0,
                    },
                ],
            )
            _write_csv(
                output_root / "cooldown_log.csv",
                [
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": "2026-02-03T04:00:00+00:00",
                        "reason": "danger_sniffed",
                        "cooldown_bars": 4,
                        "minimum_bars": 2,
                        "event_type": "cooldown_start",
                    },
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": "2026-02-03T08:00:00+00:00",
                        "reason": "danger_sniffed",
                        "cooldown_bars": 0,
                        "minimum_bars": 2,
                        "event_type": "cooldown_release",
                    },
                ],
            )
            _write_csv(
                output_root / "pyramiding_log.csv",
                [
                    {
                        "event_type": "add_on",
                        "reason": "momentum_confirmed",
                        "locked_profit": 0.0,
                        "active_trading_capital": 20400.0,
                        "cycle_id": "cycle-1",
                        "timestamp": "2026-01-01T01:00:00+00:00",
                        "symbol": "BTCUSDT",
                    },
                    {
                        "event_type": "profit_lock",
                        "reason": "vault_lock",
                        "locked_profit": 500.0,
                        "active_trading_capital": 20920.0,
                        "cycle_id": "cycle-1",
                        "timestamp": "2026-02-01T04:00:00+00:00",
                        "symbol": "BTCUSDT",
                    },
                    {
                        "event_type": "profit_lock",
                        "reason": "vault_lock",
                        "locked_profit": 1800.0,
                        "active_trading_capital": 21400.0,
                        "cycle_id": "cycle-2",
                        "timestamp": "2026-03-01T06:00:00+00:00",
                        "symbol": "BTCUSDT",
                    },
                ],
            )
            _write_csv(
                output_root / "equity.csv",
                [
                    {"timestamp": "2026-01-01T00:00:00+00:00", "equity": 20000.0, "active_capital": 20000.0, "locked_profit": 0.0},
                    {"timestamp": "2026-03-01T06:00:00+00:00", "equity": 23200.0, "active_capital": 21400.0, "locked_profit": 1800.0},
                ],
            )
            (output_root / "profit_vault.json").write_text(
                json.dumps(
                    {
                        "base_capital": 20000.0,
                        "active_trading_capital": 21400.0,
                        "locked_profit": 1800.0,
                        "floating_profit": 0.0,
                    }
                ),
                encoding="utf-8",
            )
            (output_root / "daily_opportunity_definition_refinement_001").mkdir(parents=True, exist_ok=True)
            (output_root / "daily_opportunity_definition_refinement_001" / "definition_refinement_summary.json").write_text(
                json.dumps(
                    {
                        "actual_trade_frequency": {
                            "actual_trade_count": 5,
                            "actual_trade_days": 5,
                            "zero_trade_days": 2,
                            "average_actual_trades_per_day": 0.714285,
                            "average_actual_trades_per_active_day": 1.0,
                            "max_actual_trades_on_one_day": 1,
                        },
                        "missed_high_R_opportunity_count": 0,
                        "too_tight_day_count": 0,
                    }
                ),
                encoding="utf-8",
            )

            result = write_five_year_compounding_audit(
                FiveYearCompoundingAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "five_year_compounding_audit_001",
                )
            )

            self.assertTrue(result["summary"].exists())
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual(20000.0, summary["starting_capital"])
            self.assertEqual("FULL_ACTIVE_CAPITAL_FIXED_1PCT_SL", summary["compounding_model"])
            self.assertEqual(0, summary["withdrawals"])
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertTrue(summary["long_allowed"])
            self.assertTrue(summary["short_allowed"])
            self.assertEqual("active_capital_before_trade", summary["position_notional_rule"])
            self.assertEqual(2, summary["long_trade_count"])
            self.assertEqual(3, summary["short_trade_count"])
            self.assertEqual(2, summary["profit_lock_count"])
            self.assertEqual(1, summary["cooldown_count"])
            self.assertEqual(2, summary["moonshot_5R_plus_count"])
            self.assertEqual(1, summary["moonshot_8R_plus_count"])
            self.assertEqual(1, summary["moonshot_10R_plus_count"])
            self.assertTrue(summary["whether_full_active_capital_model_survives_observed_trade_sequence"])
            self.assertGreater(summary["ending_capital_under_full_active_capital_model"], summary["starting_capital"])
            self.assertGreater(summary["ending_locked_profit_under_full_active_capital_model"], 0.0)
            self.assertLess(summary["ending_active_capital_under_full_active_capital_model"], summary["ending_capital_under_full_active_capital_model"])

            with (output_root / "five_year_compounding_audit_001" / "diagnostics" / "trade_size_growth.csv").open(
                "r", encoding="utf-8"
            ) as handle:
                trade_growth_rows = list(csv.DictReader(handle))
            self.assertEqual(200.0, float(trade_growth_rows[0]["risk_eur"]))
            self.assertEqual(400.0, float(trade_growth_rows[0]["pnl_eur"]))
            self.assertGreater(float(trade_growth_rows[1]["risk_eur"]), 200.0)

            with (output_root / "five_year_compounding_audit_001" / "diagnostics" / "yearly_compounding_summary.csv").open(
                "r", encoding="utf-8"
            ) as handle:
                yearly_rows = list(csv.DictReader(handle))
            self.assertEqual(5, len(yearly_rows))

            asymmetric = json.loads(
                (output_root / "five_year_compounding_audit_001" / "diagnostics" / "asymmetric_payoff_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn("few_winners_cover_many_losses_count", asymmetric)
            self.assertIn("moonshot_saved_block_count", asymmetric)

    def test_empty_state_writes_safe_research_only_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / "structural_compounding_lab"
            output_root = package_root / "output"
            output_root.mkdir(parents=True, exist_ok=True)

            result = write_five_year_compounding_audit(
                FiveYearCompoundingAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "five_year_compounding_audit_001",
                )
            )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            status = json.loads(result["status"].read_text(encoding="utf-8"))
            self.assertEqual("NOT_READY_FOR_COMPOUNDING", summary["compounding_readiness_classification"])
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertEqual("empty", status["state"])
            self.assertIn("no_usable_trades_for_compounding_audit", summary["warnings"])


if __name__ == "__main__":
    unittest.main()
