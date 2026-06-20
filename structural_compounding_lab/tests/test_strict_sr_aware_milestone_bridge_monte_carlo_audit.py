import json
import tempfile
import unittest
from pathlib import Path

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


class StrictSRAwareMilestoneBridgeMonteCarloAuditTests(unittest.TestCase):
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

            result = write_strict_sr_aware_milestone_bridge_monte_carlo_audit(
                StrictSRAwareMilestoneBridgeMonteCarloAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "strict_sr_aware_milestone_bridge_monte_carlo_audit_001",
                    total_path_count=1000,
                )
            )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertTrue(summary["bridge_reconstruction_result"])
            self.assertEqual("NO_LEAKAGE_DETECTED", summary["no_leakage_verdict"])
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertFalse(summary["paper_allowed"])
            self.assertFalse(summary["live_allowed"])
            self.assertFalse(summary["behavior_change_allowed"])
            self.assertIn(
                summary["final_classification"],
                {
                    "BRIDGE_REJECTED",
                    "BRIDGE_WEAK",
                    "BRIDGE_PROMISING_BUT_FRAGILE",
                    "BRIDGE_1M_PROMISING_RESEARCH_ONLY",
                    "BRIDGE_3M_OPTIMISTIC_RESEARCH_ONLY",
                    "BRIDGE_READY_FOR_SHADOW_FORWARD_SPEC_RESEARCH_ONLY",
                    "BRIDGE_NEEDS_MORE_RESEARCH_BEFORE_SHADOW",
                },
            )

            diagnostics_root = output_root / "strict_sr_aware_milestone_bridge_monte_carlo_audit_001" / "diagnostics"
            ledger_root = output_root / "strict_sr_aware_milestone_bridge_monte_carlo_audit_001" / "ledger"
            reports_root = output_root / "strict_sr_aware_milestone_bridge_monte_carlo_audit_001" / "reports"
            for path in (
                diagnostics_root / "frozen_milestone_bridge_spec.json",
                diagnostics_root / "milestone_bridge_no_future_leakage_check.json",
                ledger_root / "milestone_bridge_trades.csv",
                ledger_root / "milestone_bridge_equity.csv",
                ledger_root / "milestone_bridge_summary.json",
                diagnostics_root / "bridge_reconstruction_check.json",
                diagnostics_root / "monte_carlo_bridge_summary.json",
                diagnostics_root / "monte_carlo_bridge_paths.csv",
                diagnostics_root / "monte_carlo_mode_comparison.csv",
                diagnostics_root / "monte_carlo_failure_modes.json",
                diagnostics_root / "rolling_5y_bridge_retest.csv",
                diagnostics_root / "rolling_5y_bridge_hit_matrix.csv",
                diagnostics_root / "rolling_5y_bridge_best_worst_windows.csv",
                diagnostics_root / "milestone_bridge_fragility_audit.json",
                diagnostics_root / "risk_stepup_timing_audit.csv",
                diagnostics_root / "early_winner_dependency_audit.json",
                diagnostics_root / "drawdown_after_stepup_audit.csv",
                diagnostics_root / "missed_trade_sensitivity.csv",
                diagnostics_root / "bridge_mission_gate.json",
                diagnostics_root / "no_go_risks.json",
                reports_root / "next_research_recommendation.json",
            ):
                self.assertTrue(path.exists(), str(path))

            leakage = json.loads((diagnostics_root / "milestone_bridge_no_future_leakage_check.json").read_text(encoding="utf-8"))
            self.assertFalse(leakage["uses_future_outcome_fields"])
            gate = json.loads((diagnostics_root / "bridge_mission_gate.json").read_text(encoding="utf-8"))
            self.assertIn("conditions", gate)
            self.assertIn("passed", gate)

    def test_missing_bridge_artifacts_block_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            output_root = package_root / "output"
            output_root.mkdir(parents=True, exist_ok=True)

            result = write_strict_sr_aware_milestone_bridge_monte_carlo_audit(
                StrictSRAwareMilestoneBridgeMonteCarloAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "strict_sr_aware_milestone_bridge_monte_carlo_audit_001",
                    total_path_count=1000,
                )
            )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("STRICT_SR_AWARE_MILESTONE_BRIDGE_BLOCKED", summary["final_classification"])
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])


if __name__ == "__main__":
    unittest.main()
