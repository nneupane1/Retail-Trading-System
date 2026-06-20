import json
import tempfile
import unittest
from pathlib import Path

from structural_compounding_lab.diagnostics.cost_resilient_trade_redundancy_expansion_audit import (
    CostResilientTradeRedundancyExpansionAuditConfig,
    _normalize_rows_for_audit,
    write_cost_resilient_trade_redundancy_expansion_audit,
)
from structural_compounding_lab.diagnostics.execution_cost_realism_and_trade_redundancy_audit import (
    ExecutionCostRealismAndTradeRedundancyAuditConfig,
    write_execution_cost_realism_and_trade_redundancy_audit,
)
from structural_compounding_lab.diagnostics.milestone_bridge_fragility_driver_repair_audit import (
    MilestoneBridgeFragilityDriverRepairAuditConfig,
    write_milestone_bridge_fragility_driver_repair_audit,
)
from structural_compounding_lab.diagnostics.native_pre_entry_sr_feature_enrichment_audit import (
    NativePreEntrySRFeatureEnrichmentAuditConfig,
    write_native_pre_entry_sr_feature_enrichment_audit,
)
from structural_compounding_lab.diagnostics.native_sr_aware_5y_mission_gap_audit import (
    NativeSRAware5YMissionGapAuditConfig,
    write_native_sr_aware_5y_mission_gap_audit,
)
from structural_compounding_lab.diagnostics.native_sr_aware_strict_stress_monte_carlo_audit import (
    NativeSRAwareStrictStressMonteCarloAuditConfig,
    write_native_sr_aware_strict_stress_monte_carlo_audit,
)
from structural_compounding_lab.diagnostics.native_sr_aware_structural_replay_reproduction_audit import (
    NativeSRAwareStructuralReplayReproductionAuditConfig,
    write_native_sr_aware_structural_replay_reproduction_audit,
)
from structural_compounding_lab.diagnostics.strict_sr_aware_milestone_bridge_monte_carlo_audit import (
    StrictSRAwareMilestoneBridgeMonteCarloAuditConfig,
    write_strict_sr_aware_milestone_bridge_monte_carlo_audit,
)
from structural_compounding_lab.tests.test_native_pre_entry_sr_feature_enrichment_audit import _seed_small_fixture


class CostResilientTradeRedundancyExpansionAuditTests(unittest.TestCase):
    def test_runs_and_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root, _ = _seed_small_fixture(Path(tmpdir), with_source=True)
            output_root = package_root / "output"
            write_native_pre_entry_sr_feature_enrichment_audit(
                NativePreEntrySRFeatureEnrichmentAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "native_pre_entry_sr_feature_enrichment_audit_001",
                )
            )
            write_native_sr_aware_structural_replay_reproduction_audit(
                NativeSRAwareStructuralReplayReproductionAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "native_sr_aware_structural_replay_reproduction_audit_001",
                )
            )
            write_native_sr_aware_strict_stress_monte_carlo_audit(
                NativeSRAwareStrictStressMonteCarloAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "native_sr_aware_strict_stress_monte_carlo_audit_001",
                    monte_carlo_count=5000,
                )
            )
            write_native_sr_aware_5y_mission_gap_audit(
                NativeSRAware5YMissionGapAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "native_sr_aware_5y_mission_gap_audit_001",
                )
            )
            write_strict_sr_aware_milestone_bridge_monte_carlo_audit(
                StrictSRAwareMilestoneBridgeMonteCarloAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "strict_sr_aware_milestone_bridge_monte_carlo_audit_001",
                    total_path_count=1000,
                )
            )
            write_milestone_bridge_fragility_driver_repair_audit(
                MilestoneBridgeFragilityDriverRepairAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "milestone_bridge_fragility_driver_repair_audit_001",
                    mc_paths_per_overlay=100,
                )
            )
            write_execution_cost_realism_and_trade_redundancy_audit(
                ExecutionCostRealismAndTradeRedundancyAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "execution_cost_realism_and_trade_redundancy_audit_001",
                    random_repeat_count=8,
                )
            )

            result = write_cost_resilient_trade_redundancy_expansion_audit(
                CostResilientTradeRedundancyExpansionAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "cost_resilient_trade_redundancy_expansion_audit_001",
                    random_repeat_count=2,
                )
            )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertFalse(summary["paper_allowed"])
            self.assertFalse(summary["live_allowed"])
            self.assertFalse(summary["behavior_change_allowed"])
            self.assertTrue(summary["scout_mode"])
            self.assertFalse(summary["stochastic_budget_reliable_for_final_gate"])
            self.assertTrue(summary["deterministic_metrics_reliable"])
            self.assertFalse(summary["stochastic_metrics_reliable"])
            self.assertIn(
                summary["final_classification"],
                {
                    "REDUNDANCY_EXPANSION_REJECTED",
                    "REDUNDANCY_EXPANSION_WEAK",
                    "REDUNDANCY_EXPANSION_IMPROVES_BUT_NOT_GATE_PASSING",
                    "REDUNDANCY_EXPANSION_1M_PROMISING_RESEARCH_ONLY",
                    "REDUNDANCY_EXPANSION_READY_FOR_FINAL_NATIVE_REPLAY_RESEARCH_ONLY",
                    "REDUNDANCY_EXPANSION_NEEDS_MULTI_ASSET_OR_NEW_SLEEVE",
                },
            )

            diagnostics_root = output_root / "cost_resilient_trade_redundancy_expansion_audit_001" / "diagnostics"
            reports_root = output_root / "cost_resilient_trade_redundancy_expansion_audit_001" / "reports"
            for path in (
                diagnostics_root / "baseline_redundancy_problem_recap.json",
                diagnostics_root / "candidate_redundancy_sleeve_inventory.csv",
                diagnostics_root / "candidate_redundancy_sleeve_inventory.json",
                diagnostics_root / "candidate_sleeve_no_leakage_check.json",
                diagnostics_root / "redundancy_candidate_cost_band_results.csv",
                diagnostics_root / "redundancy_candidate_rolling_5y_results.csv",
                diagnostics_root / "redundancy_candidate_hit_matrix.csv",
                diagnostics_root / "redundancy_candidate_missed_trade_results.csv",
                diagnostics_root / "redundancy_candidate_operational_resilience.csv",
                diagnostics_root / "redundancy_improvement_scorecard.csv",
                diagnostics_root / "redundancy_improvement_scorecard.json",
                diagnostics_root / "redundancy_expansion_mission_gate.json",
                diagnostics_root / "no_go_risks.json",
                diagnostics_root / "implementation_self_audit.json",
                diagnostics_root / "stochastic_budget_reliability_check.json",
                reports_root / "next_research_recommendation.json",
            ):
                self.assertTrue(path.exists(), str(path))

            inventory_json = json.loads((diagnostics_root / "candidate_redundancy_sleeve_inventory.json").read_text(encoding="utf-8"))
            self.assertTrue(inventory_json["rows"])
            leakage_json = json.loads((diagnostics_root / "candidate_sleeve_no_leakage_check.json").read_text(encoding="utf-8"))
            self.assertTrue(all(not row["future_outcome_fields_used"] for row in leakage_json["candidates"]))
            self_audit = json.loads((diagnostics_root / "implementation_self_audit.json").read_text(encoding="utf-8"))
            self.assertTrue(self_audit["future_field_usage_check"])
            self.assertTrue(self_audit["stress_metric_scope_check"])
            reliability = json.loads((diagnostics_root / "stochastic_budget_reliability_check.json").read_text(encoding="utf-8"))
            self.assertEqual(8, reliability["random_repeat_count_used"])
            self.assertEqual(32, reliability["minimum_repeat_count_required_for_gate"])
            self.assertTrue(reliability["scout_mode"])
            self.assertFalse(reliability["stochastic_results_reliable_for_final_gate"])
            self.assertTrue(reliability["research_only"])
            self.assertFalse(reliability["real_money_allowed"])
            self.assertFalse(reliability["paper_allowed"])
            self.assertFalse(reliability["live_allowed"])
            self.assertFalse(reliability["behavior_change_allowed"])
            self.assertIn("candidate inventory", reliability["deterministic_metrics_still_usable"])
            self.assertIn("BTC-only filler redundancy did not beat the baseline", reliability["deterministic_conclusion"])
            recap = json.loads((diagnostics_root / "baseline_redundancy_problem_recap.json").read_text(encoding="utf-8"))
            self.assertIn("normal-cost rolling 5Y mission falls below 1M", recap["current_blocker_summary"])

    def test_missing_artifacts_block_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            output_root = package_root / "output"
            output_root.mkdir(parents=True, exist_ok=True)
            result = write_cost_resilient_trade_redundancy_expansion_audit(
                CostResilientTradeRedundancyExpansionAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "cost_resilient_trade_redundancy_expansion_audit_001",
                    random_repeat_count=8,
                )
            )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("COST_RESILIENT_TRADE_REDUNDANCY_EXPANSION_BLOCKED", summary["final_classification"])
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])

    def test_timestamp_fallback_works_when_exit_missing(self) -> None:
        rows = [
            {"trade_id": "A", "timestamp": "2024-01-10T12:00:00Z", "applied_r": "1.2"},
            {"trade_id": "B", "entry_timestamp": "2024-02-11T12:00:00Z", "r_multiple": "0.8"},
        ]
        normalized, schema_info, warnings, errors = _normalize_rows_for_audit(rows, require_trade_id=True)
        self.assertFalse(errors)
        self.assertEqual("timestamp", schema_info["timestamp_field_used"])
        self.assertEqual("2024-01", normalized[0]["exit_timestamp"].strftime("%Y-%m"))
        self.assertEqual("2024-02", normalized[1]["exit_timestamp"].strftime("%Y-%m"))
        self.assertTrue(any("applied_r fallback" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()
