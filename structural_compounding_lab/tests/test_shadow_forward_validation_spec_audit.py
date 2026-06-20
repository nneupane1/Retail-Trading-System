import csv
import json
import tempfile
import unittest
from pathlib import Path

from structural_compounding_lab.diagnostics.shadow_forward_validation_spec_audit import (
    OUTPUT_FOLDER_NAME,
    ShadowForwardValidationSpecAuditConfig,
    write_shadow_forward_validation_spec_audit,
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


def _seed_prior_artifacts(package_root: Path) -> None:
    output_root = package_root / "output"
    _write_csv(
        output_root / "execution_cost_realism_and_trade_redundancy_audit_001" / "diagnostics" / "execution_cost_band_results.csv",
        [
            {
                "band_name": "NORMAL_MIXED_MAKER_TAKER_COST",
                "rolling_5y_average_ending_equity": 792824.56,
                "rolling_5y_median_ending_equity": 786049.45,
                "hit_1m_windows": 12,
            }
        ],
    )
    htf_root = output_root / "htf_context_role_reconciliation_audit_001"
    htf_root.mkdir(parents=True, exist_ok=True)
    (htf_root / "htf_context_role_reconciliation_summary.json").write_text(
        json.dumps(
            {
                "final_classification": "SIX_H_CONTEXT_IMPROVES_1H_RESEARCH_ONLY",
                "best_context_variant": "LIGHT_BOOST_6H_CONFLUENCE",
                "best_context_timeframe": "6H",
                "best_normal_cost_average": 881465.53,
                "best_normal_cost_median": 878431.05,
                "best_hit_1m_windows": 18,
            }
        ),
        encoding="utf-8",
    )
    (htf_root / "diagnostics").mkdir(parents=True, exist_ok=True)
    (htf_root / "diagnostics" / "strategic_timeframe_recommendation.json").write_text(
        json.dumps(
            {
                "six_hour_should_be_official_context": True,
                "four_hour_or_six_hour_preferred": "6H",
                "twelve_hour_context_decision": "TWELVE_H_EXECUTION_RETIRED_CONTEXT_REJECTED",
                "best_context_variant": "LIGHT_BOOST_6H_CONFLUENCE",
                "six_hour_native_execution_scout_should_wait": True,
                "next_step": "shadow_forward_validation_of_accepted_1h_engine",
                "aggressive_post_300k_gear_remains_shadow_logged_only": True,
            }
        ),
        encoding="utf-8",
    )
    six_hour_root = output_root / "six_hour_native_execution_tide_context_audit_001"
    six_hour_root.mkdir(parents=True, exist_ok=True)
    (six_hour_root / "six_hour_native_execution_tide_context_summary.json").write_text(
        json.dumps(
            {
                "final_classification": "SIX_H_NATIVE_EXECUTION_WEAK",
                "best_combined_average": 169761.73,
                "best_combined_median": 168802.54,
                "best_combined_hit_1m_windows": 0,
                "six_h_native_execution_role_decision": "SIX_H_NATIVE_EXECUTION_WEAK",
                "deserves_future_capital_routing_audit": False,
                "twelve_hour_ocean_role_decision": "TWELVE_H_EXECUTION_RETIRED_CONTEXT_DIAGNOSTIC_ONLY",
                "daily_tide_role_decision": "DAILY_TIDE_CONTEXT_DIAGNOSTIC_ONLY",
                "weekly_deep_current_role_decision": "WEEKLY_DEEP_CURRENT_DIAGNOSTIC_ONLY",
            }
        ),
        encoding="utf-8",
    )
    (six_hour_root / "diagnostics").mkdir(parents=True, exist_ok=True)
    (six_hour_root / "diagnostics" / "strategic_execution_stack_recommendation.json").write_text(
        json.dumps(
            {
                "one_hour_remains_main_execution_engine": True,
                "six_hour_deserves_native_execution_scout_status": False,
                "six_hour_deserves_future_capital_routing_audit": False,
                "shadow_forward_fallback_recommended": True,
                "twelve_hour_execution_remains_retired": True,
                "aggressive_post_300k_gear_remains_shadow_logged_only": True,
                "next_step": "shadow_forward_validation_of_accepted_1h_plus_6h_context_stack",
            }
        ),
        encoding="utf-8",
    )
    earned_root = output_root / "earned_gear_activation_discovery_audit_001"
    earned_root.mkdir(parents=True, exist_ok=True)
    (earned_root / "earned_gear_activation_discovery_summary.json").write_text(
        json.dumps(
            {
                "final_classification": "EARNED_GEAR_DISCOVERY_IMPROVES_BUT_FRAGILE",
                "aggressive_gear_shadow_log_only": True,
                "best_earned_gear_average": 1017260.02,
                "best_earned_gear_median": 1053204.90,
            }
        ),
        encoding="utf-8",
    )


class ShadowForwardValidationSpecAuditTests(unittest.TestCase):
    def test_complete_run_writes_shadow_spec_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            _seed_prior_artifacts(package_root)
            result = write_shadow_forward_validation_spec_audit(
                ShadowForwardValidationSpecAuditConfig(
                    package_root=package_root,
                    output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
                )
            )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("SHADOW_SPEC_READY_WITH_6H_CONTEXT_RESEARCH_ONLY", summary["final_classification"])
            self.assertTrue(summary["prior_baseline_loaded"])
            self.assertTrue(summary["six_h_context_court_loaded"])
            self.assertTrue(summary["six_h_native_execution_court_loaded"])
            self.assertTrue(summary["earned_gear_court_loaded"])
            self.assertTrue(summary["replay_vs_forward_consistency_defined"])
            self.assertTrue(summary["operational_risk_register_defined"])
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertFalse(summary["paper_allowed"])
            self.assertFalse(summary["live_allowed"])
            self.assertFalse(summary["behavior_change_allowed"])

            diagnostics_root = package_root / "output" / OUTPUT_FOLDER_NAME / "diagnostics"
            reports_root = package_root / "output" / OUTPUT_FOLDER_NAME / "reports"
            checkpoints_root = package_root / "output" / OUTPUT_FOLDER_NAME / "_checkpoints"
            expected_paths = [
                diagnostics_root / "prior_court_anchor.json",
                diagnostics_root / "shadow_forward_architecture_spec.json",
                diagnostics_root / "shadow_log_schema.json",
                diagnostics_root / "shadow_report_templates.json",
                diagnostics_root / "shadow_readiness_gates.json",
                diagnostics_root / "replay_vs_forward_consistency_spec.json",
                diagnostics_root / "shadow_operational_risk_register.csv",
                diagnostics_root / "shadow_forward_decision.json",
                diagnostics_root / "implementation_self_audit.json",
                reports_root / "daily_report_template.md",
                reports_root / "weekly_report_template.md",
                reports_root / "monthly_report_template.md",
                reports_root / "cumulative_report_template.md",
                reports_root / "next_research_recommendation.json",
                checkpoints_root / "checkpoint_index.json",
                package_root / "output" / OUTPUT_FOLDER_NAME / "status.json",
                package_root / "output" / OUTPUT_FOLDER_NAME / "scenario_progress.json",
                package_root / "output" / OUTPUT_FOLDER_NAME / "shadow_forward_validation_spec_report.md",
            ]
            for path in expected_paths:
                self.assertTrue(path.exists(), str(path))

            log_schema = json.loads((diagnostics_root / "shadow_log_schema.json").read_text(encoding="utf-8"))
            self.assertIn("ledger/shadow_signal_log.csv", log_schema)
            self.assertIn("ledger/shadow_context_log.csv", log_schema)
            self.assertIn("ledger/shadow_research_overlay_log.csv", log_schema)
            self.assertIn("ledger/shadow_data_quality_log.csv", log_schema)
            self.assertTrue(log_schema["ledger/shadow_research_overlay_log.csv"]["required_constant_values"]["aggressive_300k_shadow_only"])

            readiness = json.loads((diagnostics_root / "shadow_readiness_gates.json").read_text(encoding="utf-8"))
            self.assertEqual(12, len(readiness["gates"]))
            self.assertTrue(readiness["not_passed_yet"])

            self_audit = json.loads((diagnostics_root / "implementation_self_audit.json").read_text(encoding="utf-8"))
            self.assertTrue(self_audit["no_order_path_created"])
            self.assertTrue(self_audit["no_paper_path_created"])
            self.assertTrue(self_audit["no_live_path_created"])
            self.assertFalse(self_audit["previous_artifacts_overwritten"])

    def test_missing_prior_court_blocks_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            _seed_prior_artifacts(package_root)
            earned_path = package_root / "output" / "earned_gear_activation_discovery_audit_001" / "earned_gear_activation_discovery_summary.json"
            earned_path.unlink()

            result = write_shadow_forward_validation_spec_audit(
                ShadowForwardValidationSpecAuditConfig(
                    package_root=package_root,
                    output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
                )
            )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            status = json.loads(result["status"].read_text(encoding="utf-8"))
            self.assertEqual("SHADOW_SPEC_BLOCKED", summary["final_classification"])
            self.assertEqual("blocked", status["state"])
            self.assertFalse(summary["prior_baseline_loaded"])
            self.assertTrue(any("Earned gear court summary missing." in warning for warning in summary["warnings"]))
            diagnostics_root = package_root / "output" / OUTPUT_FOLDER_NAME / "diagnostics"
            self.assertTrue((diagnostics_root / "implementation_self_audit.json").exists())


if __name__ == "__main__":
    unittest.main()
