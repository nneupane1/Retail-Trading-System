import csv
import json
import tempfile
import unittest
from pathlib import Path

from structural_compounding_lab.diagnostics.broad_frozen_patch_validation import (
    BroadFrozenPatchValidationConfig,
    write_broad_frozen_patch_validation,
)
from structural_compounding_lab.diagnostics.broad_patch_bluntness_audit import (
    BroadPatchBluntnessAuditConfig,
    write_broad_patch_bluntness_audit,
)
from structural_compounding_lab.tests.test_broad_frozen_patch_validation import (
    _build_trade_fixture,
    _write_csv,
)


class BroadPatchBluntnessAuditTests(unittest.TestCase):
    def test_broad_patch_bluntness_audit_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / "structural_compounding_lab"
            output_root = package_root / "output"
            broad_root = output_root / "broad_historical_structural_replay_001"
            broad_ledger_root = broad_root / "ledger"
            broad_diag_root = broad_root / "diagnostics"
            broad_report_root = broad_root / "reports"
            frozen_root = output_root / "frozen_patch_validation_audit_001" / "diagnostics"
            broad_diag_root.mkdir(parents=True, exist_ok=True)
            broad_report_root.mkdir(parents=True, exist_ok=True)
            frozen_root.mkdir(parents=True, exist_ok=True)

            trades, setups, levels, liquidity = _build_trade_fixture()
            _write_csv(broad_ledger_root / "trades.csv", trades)
            _write_csv(broad_ledger_root / "setup_log.csv", setups)
            _write_csv(broad_ledger_root / "level_log.csv", levels)
            _write_csv(broad_ledger_root / "liquidity_events.csv", liquidity)
            _write_csv(
                broad_ledger_root / "cooldown_log.csv",
                [{"symbol": "BTCUSDT", "timestamp": "2023-01-01T00:00:00+00:00", "reason": "danger_sniffed", "cooldown_bars": 4, "minimum_bars": 2, "event_type": "cooldown_start"}],
            )
            _write_csv(
                broad_ledger_root / "pyramiding_log.csv",
                [{"symbol": "BTCUSDT", "timestamp": "2024-01-01T00:00:00+00:00", "event_type": "profit_lock", "locked_profit": 600.0, "active_trading_capital": 20000.0, "convexity_label": "elite_convexity"}],
            )
            _write_csv(
                broad_ledger_root / "equity.csv",
                [{"timestamp": "2021-01-01T00:00:00+00:00", "equity": 20000.0}, {"timestamp": "2024-01-01T00:00:00+00:00", "equity": 26000.0}],
            )
            (broad_ledger_root / "summary.json").write_text(
                json.dumps(
                    {
                        "ending_equity": 26000.0,
                        "current_equity": 26000.0,
                        "active_trading_capital": 21000.0,
                        "locked_profit": 5000.0,
                        "floating_profit": 0.0,
                        "trade_count": len(trades),
                        "profit_lock_count": 1,
                        "add_on_event_count": 0,
                        "cooldown_event_count": 1,
                        "metrics": {
                            "profit_factor": 1.18,
                            "avg_r": 0.11,
                            "max_drawdown_pct": 0.16,
                        },
                    }
                ),
                encoding="utf-8",
            )
            (broad_ledger_root / "profit_vault.json").write_text(
                json.dumps(
                    {
                        "base_capital": 20000.0,
                        "active_trading_capital": 21000.0,
                        "locked_profit": 5000.0,
                        "floating_profit": 0.0,
                        "current_compounding_cycle_id": "cycle-4",
                    }
                ),
                encoding="utf-8",
            )
            (broad_ledger_root / "execution_realism").mkdir(parents=True, exist_ok=True)
            (broad_ledger_root / "execution_realism" / "execution_cost_sensitivity.json").write_text(
                json.dumps(
                    {
                        "scenario_metrics": {
                            "low_cost": {"net_pnl_after_costs": -500.0, "profit_factor_after_costs": 0.9, "average_cost_per_trade": 10.0, "total_fees": 120.0, "total_estimated_slippage": 80.0},
                            "normal_cost": {"net_pnl_after_costs": -1600.0, "profit_factor_after_costs": 0.7, "average_cost_per_trade": 20.0, "total_fees": 200.0, "total_estimated_slippage": 140.0},
                            "high_cost": {"net_pnl_after_costs": -2600.0, "profit_factor_after_costs": 0.55, "average_cost_per_trade": 28.0, "total_fees": 260.0, "total_estimated_slippage": 180.0},
                            "stress_cost": {"net_pnl_after_costs": -3600.0, "profit_factor_after_costs": 0.42, "average_cost_per_trade": 35.0, "total_fees": 340.0, "total_estimated_slippage": 260.0},
                        }
                    }
                ),
                encoding="utf-8",
            )
            (broad_root / "broad_historical_replay_summary.json").write_text(
                json.dumps(
                    {
                        "source_data_start": "2018-01-01T00:00:00",
                        "source_data_end": "2026-06-13T00:00:00",
                        "generated_ledger_start": "2021-01-01T00:00:00",
                        "generated_ledger_end": "2026-06-13T00:00:00",
                        "trade_count": len(trades),
                        "long_trade_count": 24,
                        "short_trade_count": 24,
                        "coverage_sufficient_for_frozen_patch_validation": True,
                    }
                ),
                encoding="utf-8",
            )
            (broad_diag_root / "replay_health_report.json").write_text(
                json.dumps({"successful_replay": True, "safe_for_frozen_patch_validation": True}),
                encoding="utf-8",
            )
            (broad_report_root / "next_research_recommendation.json").write_text(
                json.dumps({"next_step": "APPLY_FROZEN_PATCH_TO_BROAD_HISTORICAL_LEDGER"}),
                encoding="utf-8",
            )
            (frozen_root / "frozen_patch_rules.json").write_text(
                json.dumps(
                    {
                        "frozen_patch_candidate": "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT",
                        "source_recommendation": "PRESERVE_PROVEN_SHORTS_ONLY",
                        "disabled_long_failure_modes": [
                            "LONG_COST_DOMINATED",
                            "LONG_COUNTER_HTF",
                            "LONG_DANGER_TOO_HIGH",
                            "LONG_EMA_FAKEOUT",
                            "LONG_OVERHEAD_RESISTANCE_TOO_CLOSE",
                            "LONG_TINY_STOP_TRAP",
                            "LONG_VWAP_FAKEOUT",
                            "LONG_WEAK_RECLAIM",
                        ],
                        "short_bucket_rule": {
                            "trade_count_min": 20,
                            "total_R_gt": 0.0,
                            "profit_factor_gt": 1.1,
                            "avg_R_gt": 0.0,
                            "matched_archetype_keys": [
                                "short|sweep_high|elite_convexity|resistance|equal_highs"
                            ],
                        },
                        "frozen_without_retuning": True,
                    }
                ),
                encoding="utf-8",
            )

            write_broad_frozen_patch_validation(
                BroadFrozenPatchValidationConfig(
                    package_root=package_root,
                    output_root=output_root / "broad_frozen_patch_validation_001",
                )
            )
            result = write_broad_patch_bluntness_audit(
                BroadPatchBluntnessAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "broad_patch_bluntness_audit_001",
                )
            )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            no_go = json.loads((output_root / "broad_patch_bluntness_audit_001" / "diagnostics" / "no_go_risks.json").read_text(encoding="utf-8"))
            accounting = json.loads((output_root / "broad_patch_bluntness_audit_001" / "diagnostics" / "equity_explosion_accounting_audit.json").read_text(encoding="utf-8"))

            self.assertTrue(summary["research_only"])
            self.assertIn(
                summary["final_classification"],
                {
                    "PATCH_ACCOUNTING_NEEDS_RECONCILIATION",
                    "PATCH_STRONG_BUT_TOO_BLUNT",
                    "PATCH_STRONG_AND_SHORT_RESCUE_PROMISING",
                    "PATCH_STRONG_BUT_MOONSHOT_DEPENDENT",
                    "PATCH_REJECTED_AFTER_BLUNTNESS_AUDIT",
                },
            )
            self.assertIn("flags", no_go)
            self.assertIn("interpretation", accounting)

            with (output_root / "broad_patch_bluntness_audit_001" / "diagnostics" / "removed_winners_by_archetype_year.csv").open("r", encoding="utf-8") as handle:
                removed_winners_rows = list(csv.DictReader(handle))
            self.assertIsInstance(removed_winners_rows, list)

            with (output_root / "broad_patch_bluntness_audit_001" / "diagnostics" / "removed_losers_by_failure_mode_year.csv").open("r", encoding="utf-8") as handle:
                removed_losers_rows = list(csv.DictReader(handle))
            self.assertTrue(removed_losers_rows)

            with (output_root / "broad_patch_bluntness_audit_001" / "diagnostics" / "variant_replay_comparison.csv").open("r", encoding="utf-8") as handle:
                variant_rows = list(csv.DictReader(handle))
            self.assertTrue(any(row["variant_name"] == "FROZEN_PATCH_RESCUE_SHORTS_R_GE_5" for row in variant_rows))


if __name__ == "__main__":
    unittest.main()
