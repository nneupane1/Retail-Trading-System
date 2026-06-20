import csv
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
from structural_compounding_lab.tests.test_native_pre_entry_sr_feature_enrichment_audit import _seed_small_fixture


class NativeSRAwareStructuralReplayReproductionAuditTests(unittest.TestCase):
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
            broad_summary_path = output_root / "broad_historical_structural_replay_001" / "ledger" / "summary.json"
            broad_before = broad_summary_path.read_text(encoding="utf-8")

            result = write_native_sr_aware_structural_replay_reproduction_audit(
                NativeSRAwareStructuralReplayReproductionAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "native_sr_aware_structural_replay_reproduction_audit_001",
                )
            )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertFalse(summary["paper_allowed"])
            self.assertFalse(summary["live_allowed"])
            self.assertFalse(summary["behavior_change_allowed"])
            self.assertTrue(summary["isolated_native_sr_aware_replay_ran"])
            self.assertIn(
                summary["final_classification"],
                {
                    "NATIVE_SR_REPLAY_BLOCKED",
                    "NATIVE_SR_REPLAY_REJECTED",
                    "NATIVE_SR_REPLAY_WEAK",
                    "NATIVE_SR_REPLAY_IMPROVES_BUT_NOT_MISSION_MOVING",
                    "NATIVE_SR_REPLAY_1M_PROMISING_RESEARCH_ONLY",
                    "NATIVE_SR_REPLAY_READY_FOR_STRESS_MONTE_CARLO_RESEARCH_ONLY",
                    "NATIVE_SR_REPLAY_ABANDON_EQUAL_HIGHS_PATH",
                },
            )

            diagnostics_root = output_root / "native_sr_aware_structural_replay_reproduction_audit_001" / "diagnostics"
            ledger_root = output_root / "native_sr_aware_structural_replay_reproduction_audit_001" / "ledger"
            self.assertTrue((diagnostics_root / "sr_aware_research_spec.json").exists())
            self.assertTrue((diagnostics_root / "sr_aware_spec_no_leakage_check.json").exists())
            self.assertTrue((ledger_root / "native_sr_aware_trades.csv").exists())
            self.assertTrue((ledger_root / "native_sr_aware_equity.csv").exists())
            self.assertTrue((diagnostics_root / "native_sr_aware_variant_comparison.csv").exists())
            self.assertTrue((diagnostics_root / "native_sr_aware_rolling_5y_results.csv").exists())
            self.assertTrue((diagnostics_root / "native_sr_aware_cost_survival.csv").exists())
            self.assertTrue((diagnostics_root / "native_sr_aware_moonshot_survival.csv").exists())
            self.assertTrue((diagnostics_root / "native_sr_aware_drawdown_governor.csv").exists())
            self.assertTrue((diagnostics_root / "native_sr_aware_insolvency_clamp.csv").exists())

            no_leak = json.loads((diagnostics_root / "sr_aware_spec_no_leakage_check.json").read_text(encoding="utf-8"))
            self.assertTrue(no_leak["final_no_leakage_verdict"])

            with (diagnostics_root / "native_sr_aware_variant_comparison.csv").open("r", encoding="utf-8") as handle:
                self.assertTrue(list(csv.DictReader(handle)))
            with (ledger_root / "native_sr_aware_trades.csv").open("r", encoding="utf-8") as handle:
                self.assertTrue(list(csv.DictReader(handle)))

            self.assertEqual(broad_before, broad_summary_path.read_text(encoding="utf-8"))

    def test_missing_source_blocks_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root, _ = _seed_small_fixture(Path(tmpdir), with_source=False)
            output_root = package_root / "output"
            result = write_native_sr_aware_structural_replay_reproduction_audit(
                NativeSRAwareStructuralReplayReproductionAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "native_sr_aware_structural_replay_reproduction_audit_001",
                )
            )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("NATIVE_SR_REPLAY_BLOCKED", summary["final_classification"])


if __name__ == "__main__":
    unittest.main()
