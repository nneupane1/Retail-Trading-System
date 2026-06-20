import csv
import json
import tempfile
import unittest
from pathlib import Path

from structural_compounding_lab.diagnostics.broad_frozen_patch_validation import (
    BroadFrozenPatchValidationConfig,
    write_broad_frozen_patch_validation,
)
from structural_compounding_lab.diagnostics.broad_patch_accounting_and_short_rescue_audit import (
    BroadPatchAccountingAndShortRescueAuditConfig,
    write_broad_patch_accounting_and_short_rescue_audit,
)
from structural_compounding_lab.diagnostics.broad_patch_bluntness_audit import (
    BroadPatchBluntnessAuditConfig,
    write_broad_patch_bluntness_audit,
)
from structural_compounding_lab.tests.test_broad_frozen_patch_validation import (
    _build_trade_fixture,
    _write_csv,
)


class BroadPatchAccountingAndShortRescueAuditTests(unittest.TestCase):
    def test_audit_writes_required_outputs(self) -> None:
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
                        "metrics": {"profit_factor": 1.18, "avg_r": 0.11, "max_drawdown_pct": 0.16},
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
                    }
                ),
                encoding="utf-8",
            )
            (broad_ledger_root / "execution_realism").mkdir(parents=True, exist_ok=True)
            (broad_ledger_root / "execution_realism" / "execution_cost_sensitivity.json").write_text(
                json.dumps(
                    {
                        "scenario_metrics": {
                            "low_cost": {"net_pnl_after_costs": -500.0},
                            "normal_cost": {"net_pnl_after_costs": -1600.0},
                            "high_cost": {"net_pnl_after_costs": -2600.0},
                            "stress_cost": {"net_pnl_after_costs": -3600.0},
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
            (broad_diag_root / "replay_health_report.json").write_text(json.dumps({"successful_replay": True, "safe_for_frozen_patch_validation": True}), encoding="utf-8")
            (broad_report_root / "next_research_recommendation.json").write_text(json.dumps({"next_step": "APPLY_FROZEN_PATCH_TO_BROAD_HISTORICAL_LEDGER"}), encoding="utf-8")
            (frozen_root / "frozen_patch_rules.json").write_text(
                json.dumps(
                    {
                        "frozen_patch_candidate": "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT",
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
                            "matched_archetype_keys": ["short|sweep_high|elite_convexity|resistance|equal_highs"]
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
            write_broad_patch_bluntness_audit(
                BroadPatchBluntnessAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "broad_patch_bluntness_audit_001",
                )
            )
            result = write_broad_patch_accounting_and_short_rescue_audit(
                BroadPatchAccountingAndShortRescueAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "broad_patch_accounting_and_short_rescue_audit_001",
                )
            )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            truth = json.loads((output_root / "broad_patch_accounting_and_short_rescue_audit_001" / "diagnostics" / "equity_headline_truth_label.json").read_text(encoding="utf-8"))
            no_leak = json.loads((output_root / "broad_patch_accounting_and_short_rescue_audit_001" / "diagnostics" / "rescue_signature_no_future_leakage_check.json").read_text(encoding="utf-8"))
            rescue_defs = json.loads((output_root / "broad_patch_accounting_and_short_rescue_audit_001" / "diagnostics" / "rescue_signature_definitions.json").read_text(encoding="utf-8"))
            rescue_results = json.loads((output_root / "broad_patch_accounting_and_short_rescue_audit_001" / "diagnostics" / "rescue_signature_candidate_results.json").read_text(encoding="utf-8"))
            variant_reconciled = json.loads((output_root / "broad_patch_accounting_and_short_rescue_audit_001" / "diagnostics" / "variant_comparison_reconciled.json").read_text(encoding="utf-8"))

            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertFalse(summary["paper_allowed"])
            self.assertFalse(summary["live_allowed"])
            self.assertFalse(summary["behavior_change_allowed"])
            self.assertIn(summary["equity_headline_truth_label"], {"NATIVE_ENGINE_TRUTH", "NATIVE_STYLE_RECONCILED_RESEARCH_RESULT", "FILTERED_THEORETICAL_COMPOUNDING_ONLY", "ACCOUNTING_MISMATCH_UNRESOLVED", "INVALID_REPLAY_ACCOUNTING"})
            self.assertIn(summary["final_classification"], {"ACCOUNTING_NOT_RECONCILED_STOP", "PATCH_STRONG_BUT_THEORETICAL_ONLY", "PATCH_STRONG_AFTER_NATIVE_STYLE_RECONCILIATION", "PATCH_TOO_BLUNT_SHORT_RESCUE_REQUIRED", "SHORT_RESCUE_PROMISING_RESEARCH_ONLY", "PATCH_REJECTED_AFTER_RECONCILIATION"})
            self.assertIn("label", truth)
            self.assertTrue(no_leak["all_exante_candidates_safe"])
            self.assertTrue(rescue_defs["definitions"])
            self.assertTrue(rescue_results["results"])
            self.assertTrue(any(v["oracle_not_deployable"] for v in variant_reconciled["variants"]))
            self.assertTrue(any(v["variant_name"] == "FROZEN_PATCH_RESCUE_SHORTS_ORACLE_R_GE_5" for v in variant_reconciled["variants"]))
            self.assertTrue(any(v["variant_name"] == "FROZEN_PATCH_COST_INSIDE_COMPOUNDING_NORMAL" for v in variant_reconciled["variants"]))
            self.assertTrue(any(v["variant_name"] == "FROZEN_PATCH_MOONSHOTS_CAPPED_3R" for v in variant_reconciled["variants"]))

            with (output_root / "broad_patch_accounting_and_short_rescue_audit_001" / "diagnostics" / "accounting_reconciliation_table.csv").open("r", encoding="utf-8") as handle:
                accounting_rows = list(csv.DictReader(handle))
            self.assertTrue(accounting_rows)
            self.assertTrue(any(row["variant_name"] == "FROZEN_PATCH_COST_INSIDE_COMPOUNDING_NORMAL" for row in accounting_rows))

    def test_missing_artifacts_safe_empty_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / "structural_compounding_lab"
            output_root = package_root / "output"
            output_root.mkdir(parents=True, exist_ok=True)
            result = write_broad_patch_accounting_and_short_rescue_audit(
                BroadPatchAccountingAndShortRescueAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "broad_patch_accounting_and_short_rescue_audit_001",
                )
            )
            status = json.loads(result["status"].read_text(encoding="utf-8"))
            self.assertEqual("empty", status["state"])


if __name__ == "__main__":
    unittest.main()
