import json
import tempfile
import unittest
from pathlib import Path

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


class MilestoneBridgeFragilityDriverRepairAuditTests(unittest.TestCase):
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

            result = write_milestone_bridge_fragility_driver_repair_audit(
                MilestoneBridgeFragilityDriverRepairAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "milestone_bridge_fragility_driver_repair_audit_001",
                    mc_paths_per_overlay=100,
                )
            )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertFalse(summary["paper_allowed"])
            self.assertFalse(summary["live_allowed"])
            self.assertFalse(summary["behavior_change_allowed"])
            self.assertIn(
                summary["final_classification"],
                {
                    "FRAGILITY_REPAIR_REJECTED",
                    "FRAGILITY_REPAIR_WEAK",
                    "FRAGILITY_REPAIR_IMPROVES_BUT_NOT_GATE_PASSING",
                    "FRAGILITY_REPAIR_1M_PROMISING_RESEARCH_ONLY",
                    "FRAGILITY_REPAIR_READY_FOR_SHADOW_SPEC_RESEARCH_ONLY",
                    "FRAGILITY_REPAIR_NEEDS_MORE_EDGE_OR_TRADE_REDUNDANCY",
                },
            )

            diagnostics_root = output_root / "milestone_bridge_fragility_driver_repair_audit_001" / "diagnostics"
            reports_root = output_root / "milestone_bridge_fragility_driver_repair_audit_001" / "reports"
            for path in (
                diagnostics_root / "cost_fragility_decomposition.csv",
                diagnostics_root / "cost_fragility_by_year.csv",
                diagnostics_root / "cost_fragility_by_month.csv",
                diagnostics_root / "cost_realism_assessment.json",
                diagnostics_root / "missed_trade_fragility_decomposition.csv",
                diagnostics_root / "missed_trade_rate_sensitivity.csv",
                diagnostics_root / "top_winner_dependency_decomposition.csv",
                diagnostics_root / "milestone_timing_missed_trade_sensitivity.csv",
                diagnostics_root / "trade_redundancy_score.json",
                diagnostics_root / "fragility_repair_overlay_results.csv",
                diagnostics_root / "fragility_repair_overlay_results.json",
                diagnostics_root / "fragility_repair_monte_carlo_comparison.json",
                diagnostics_root / "fragility_repair_mission_gate_comparison.csv",
                diagnostics_root / "revised_bridge_mission_gate.json",
                diagnostics_root / "no_go_risks.json",
                reports_root / "next_research_recommendation.json",
            ):
                self.assertTrue(path.exists(), str(path))

            overlay_json = json.loads((diagnostics_root / "fragility_repair_overlay_results.json").read_text(encoding="utf-8"))
            self.assertTrue(overlay_json["rows"])
            self.assertTrue(all(not row["uses_future_outcome_fields"] for row in overlay_json["rows"]))

    def test_missing_artifacts_block_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            output_root = package_root / "output"
            output_root.mkdir(parents=True, exist_ok=True)
            result = write_milestone_bridge_fragility_driver_repair_audit(
                MilestoneBridgeFragilityDriverRepairAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "milestone_bridge_fragility_driver_repair_audit_001",
                    mc_paths_per_overlay=100,
                )
            )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("MILESTONE_BRIDGE_FRAGILITY_REPAIR_BLOCKED", summary["final_classification"])
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])


if __name__ == "__main__":
    unittest.main()
