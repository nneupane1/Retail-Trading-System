import json
import tempfile
import unittest
from pathlib import Path

from structural_compounding_lab.diagnostics.native_pre_entry_sr_feature_enrichment_audit import (
    NativePreEntrySRFeatureEnrichmentAuditConfig,
    write_native_pre_entry_sr_feature_enrichment_audit,
)
from structural_compounding_lab.diagnostics.native_sr_aware_structural_replay_reproduction_audit import (
    NativeSRAwareStructuralReplayReproductionAuditConfig,
    write_native_sr_aware_structural_replay_reproduction_audit,
)
from structural_compounding_lab.diagnostics.native_sr_aware_strict_stress_monte_carlo_audit import (
    NativeSRAwareStrictStressMonteCarloAuditConfig,
    write_native_sr_aware_strict_stress_monte_carlo_audit,
)
from structural_compounding_lab.tests.test_native_pre_entry_sr_feature_enrichment_audit import _seed_small_fixture


class NativeSRAwareStrictStressMonteCarloAuditTests(unittest.TestCase):
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

            result = write_native_sr_aware_strict_stress_monte_carlo_audit(
                NativeSRAwareStrictStressMonteCarloAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "native_sr_aware_strict_stress_monte_carlo_audit_001",
                    monte_carlo_count=5000,
                )
            )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertEqual("NATIVE_SR_AWARE_STRICT", summary["variant_name"])
            self.assertGreaterEqual(summary["monte_carlo_simulation_count"], 5000)
            self.assertIn(
                summary["pf_sanity_verdict"],
                {
                    "PF_VALID",
                    "PF_VALID_BUT_FRAGILE",
                    "PF_DISTORTED_BY_LOW_LOSS_DENOMINATOR",
                    "PF_REQUIRES_MANUAL_REVIEW",
                    "PF_INVALID",
                },
            )
            self.assertIn(
                summary["pre_entry_integrity_verdict"],
                {
                    "NO_LEAKAGE_DETECTED",
                    "LIKELY_NO_LEAKAGE_BUT_MANUAL_REVIEW_REQUIRED",
                    "LEAKAGE_RISK_MODERATE",
                    "LEAKAGE_RISK_HIGH",
                    "LEAKAGE_DETECTED",
                },
            )

            diagnostics_root = output_root / "native_sr_aware_strict_stress_monte_carlo_audit_001" / "diagnostics"
            reports_root = output_root / "native_sr_aware_strict_stress_monte_carlo_audit_001" / "reports"
            for path in (
                diagnostics_root / "frozen_variant_spec.json",
                diagnostics_root / "pf_42_sanity_audit.json",
                diagnostics_root / "pre_entry_rule_integrity_audit.json",
                diagnostics_root / "stress_test_matrix.csv",
                diagnostics_root / "rolling_5y_stress_summary.csv",
                diagnostics_root / "monte_carlo_summary.json",
                diagnostics_root / "monte_carlo_distribution.csv",
                diagnostics_root / "monte_carlo_drawdown_distribution.csv",
                diagnostics_root / "monte_carlo_ruin_risk.json",
                diagnostics_root / "mission_gap_report.json",
                diagnostics_root / "promotion_gate_report.json",
                diagnostics_root / "no_go_risks.json",
                reports_root / "next_research_recommendation.json",
            ):
                self.assertTrue(path.exists(), str(path))

            gate = json.loads((diagnostics_root / "promotion_gate_report.json").read_text(encoding="utf-8"))
            self.assertFalse(gate["real_money_allowed"])
            self.assertIn(
                gate["classification"],
                {
                    "REJECT_VARIANT",
                    "KEEP_RESEARCH_ONLY",
                    "PROMISING_BUT_NOT_MISSION_MOVING",
                    "READY_FOR_EXTENDED_PAPER_SIMULATION",
                    "READY_FOR_SMALL_CAPITAL_TRIAL_RESEARCH_ONLY",
                },
            )

    def test_missing_source_artifacts_write_safe_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            output_root = package_root / "output"
            output_root.mkdir(parents=True, exist_ok=True)

            result = write_native_sr_aware_strict_stress_monte_carlo_audit(
                NativeSRAwareStrictStressMonteCarloAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "native_sr_aware_strict_stress_monte_carlo_audit_001",
                )
            )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("NATIVE_SR_AWARE_STRICT_STRESS_BLOCKED", summary["final_classification"])
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])


if __name__ == "__main__":
    unittest.main()
