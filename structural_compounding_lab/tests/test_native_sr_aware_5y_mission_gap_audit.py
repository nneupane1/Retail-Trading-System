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
from structural_compounding_lab.tests.test_native_pre_entry_sr_feature_enrichment_audit import _seed_small_fixture


class NativeSRAware5YMissionGapAuditTests(unittest.TestCase):
    def test_runs_and_writes_expected_outputs(self) -> None:
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
            strict_result = write_native_sr_aware_strict_stress_monte_carlo_audit(
                NativeSRAwareStrictStressMonteCarloAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "native_sr_aware_strict_stress_monte_carlo_audit_001",
                    monte_carlo_count=5000,
                )
            )
            strict_summary_before = strict_result["summary"].read_text(encoding="utf-8")

            result = write_native_sr_aware_5y_mission_gap_audit(
                NativeSRAware5YMissionGapAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "native_sr_aware_5y_mission_gap_audit_001",
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
                    "FIVE_YEAR_GAP_NOT_BRIDGEABLE",
                    "FIVE_YEAR_GAP_BRIDGE_WEAK",
                    "FIVE_YEAR_GAP_BRIDGE_PROMISING_RESEARCH_ONLY",
                    "FIVE_YEAR_GAP_NEEDS_MORE_TRADE_FREQUENCY",
                    "FIVE_YEAR_GAP_NEEDS_CAPITAL_DEPLOYMENT_REPAIR",
                    "FIVE_YEAR_GAP_NEEDS_COMPLEMENTARY_LONG_OR_SHORT_SLEEVE",
                    "FIVE_YEAR_GAP_READY_FOR_MONTE_CARLO_RETEST_RESEARCH_ONLY",
                },
            )

            diagnostics_root = output_root / "native_sr_aware_5y_mission_gap_audit_001" / "diagnostics"
            reports_root = output_root / "native_sr_aware_5y_mission_gap_audit_001" / "reports"
            for path in (
                diagnostics_root / "full_sequence_vs_5y_gap_attribution.json",
                diagnostics_root / "yearly_contribution_timeline.csv",
                diagnostics_root / "monthly_contribution_timeline.csv",
                diagnostics_root / "trade_frequency_timeline.csv",
                diagnostics_root / "top_winner_timing.csv",
                diagnostics_root / "inactive_periods.csv",
                diagnostics_root / "rolling_5y_gap_decomposition.csv",
                diagnostics_root / "rolling_5y_gap_decomposition.json",
                diagnostics_root / "closest_windows_to_1m.csv",
                diagnostics_root / "farthest_windows_from_1m.csv",
                diagnostics_root / "mission_bridge_variant_results.csv",
                diagnostics_root / "mission_bridge_variant_results.json",
                diagnostics_root / "mission_bridge_rolling_5y_results.csv",
                diagnostics_root / "mission_bridge_risk_multiplier_audit.csv",
                diagnostics_root / "mission_bridge_insolvency_clamp_audit.csv",
                diagnostics_root / "mission_realism_gate.json",
                diagnostics_root / "no_go_risks.json",
                reports_root / "next_research_recommendation.json",
            ):
                self.assertTrue(path.exists(), str(path))

            bridge_payload = json.loads((diagnostics_root / "mission_bridge_variant_results.json").read_text(encoding="utf-8"))
            rows = bridge_payload["rows"]
            self.assertTrue(rows)
            non_oracle = [row for row in rows if not row["uses_future_outcome_info"]]
            self.assertTrue(non_oracle)
            self.assertTrue(all(not row["uses_future_outcome_info"] for row in non_oracle))
            self.assertTrue(any(row["uses_future_outcome_info"] for row in rows))

            realism_gate = json.loads((diagnostics_root / "mission_realism_gate.json").read_text(encoding="utf-8"))
            self.assertIn("gate_rows", realism_gate)
            self.assertIn("accepted_variants", realism_gate)

            strict_summary_after = strict_result["summary"].read_text(encoding="utf-8")
            self.assertEqual(strict_summary_before, strict_summary_after)

    def test_missing_strict_sequence_writes_safe_blocked_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            output_root = package_root / "output"
            output_root.mkdir(parents=True, exist_ok=True)

            result = write_native_sr_aware_5y_mission_gap_audit(
                NativeSRAware5YMissionGapAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "native_sr_aware_5y_mission_gap_audit_001",
                )
            )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("NATIVE_SR_AWARE_5Y_MISSION_GAP_BLOCKED", summary["final_classification"])
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])


if __name__ == "__main__":
    unittest.main()
