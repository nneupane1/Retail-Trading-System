import json
import tempfile
import unittest
from pathlib import Path

from structural_compounding_lab.diagnostics.execution_cost_realism_and_trade_redundancy_audit import (
    ExecutionCostRealismAndTradeRedundancyAuditConfig,
    _normalize_rows_for_audit,
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


class ExecutionCostRealismAndTradeRedundancyAuditTests(unittest.TestCase):
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

            result = write_execution_cost_realism_and_trade_redundancy_audit(
                ExecutionCostRealismAndTradeRedundancyAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "execution_cost_realism_and_trade_redundancy_audit_001",
                    random_repeat_count=8,
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
                    "EXECUTION_REDUNDANCY_REJECTED",
                    "EXECUTION_REDUNDANCY_WEAK",
                    "EXECUTION_REDUNDANCY_COST_REALISTIC_BUT_LOW_REDUNDANCY",
                    "EXECUTION_REDUNDANCY_1M_PROMISING_RESEARCH_ONLY",
                    "EXECUTION_REDUNDANCY_READY_FOR_SHADOW_REPORTING_SPEC_RESEARCH_ONLY",
                    "EXECUTION_REDUNDANCY_NEEDS_MORE_TRADE_FREQUENCY",
                },
            )

            diagnostics_root = output_root / "execution_cost_realism_and_trade_redundancy_audit_001" / "diagnostics"
            reports_root = output_root / "execution_cost_realism_and_trade_redundancy_audit_001" / "reports"
            for path in (
                diagnostics_root / "execution_cost_model_assumptions.json",
                diagnostics_root / "execution_cost_band_results.csv",
                diagnostics_root / "execution_cost_band_results.json",
                diagnostics_root / "cost_band_rolling_5y_survival.csv",
                diagnostics_root / "cost_band_mission_hit_matrix.csv",
                diagnostics_root / "cost_band_drawdown_report.csv",
                diagnostics_root / "missed_trade_tolerance_results.csv",
                diagnostics_root / "missed_trade_tolerance_results.json",
                diagnostics_root / "missed_trade_operational_risk_thresholds.json",
                diagnostics_root / "trade_redundancy_cluster_audit.csv",
                diagnostics_root / "trade_redundancy_concentration_report.json",
                diagnostics_root / "key_trade_cluster_dependency.json",
                diagnostics_root / "operational_reliability_requirements.json",
                diagnostics_root / "no_go_risks.json",
                diagnostics_root / "implementation_self_audit.json",
                reports_root / "future_shadow_reporting_requirements.json",
                reports_root / "next_research_recommendation.json",
            ):
                self.assertTrue(path.exists(), str(path))

            cost_json = json.loads((diagnostics_root / "execution_cost_band_results.json").read_text(encoding="utf-8"))
            self.assertTrue(cost_json["rows"])
            band_map = {row["band_name"]: row for row in cost_json["rows"]}
            self.assertGreaterEqual(
                float(band_map["ZERO_COST_REFERENCE"]["rolling_5y_average_ending_equity"]),
                float(band_map["NORMAL_MIXED_MAKER_TAKER_COST"]["rolling_5y_average_ending_equity"]),
            )
            self.assertGreaterEqual(
                float(band_map["NORMAL_MIXED_MAKER_TAKER_COST"]["rolling_5y_average_ending_equity"]),
                float(band_map["FIVE_X_PUNITIVE_COST"]["rolling_5y_average_ending_equity"]),
            )
            missed_json = json.loads((diagnostics_root / "missed_trade_tolerance_results.json").read_text(encoding="utf-8"))
            self.assertTrue(missed_json["rows"])
            missed_map = {row["scenario_name"]: row for row in missed_json["rows"]}
            self.assertGreaterEqual(
                float(missed_map["random_miss_1pct"]["rolling_5y_average_ending_equity"]),
                float(missed_map["random_miss_5pct"]["rolling_5y_average_ending_equity"]),
            )
            self_audit = json.loads((diagnostics_root / "implementation_self_audit.json").read_text(encoding="utf-8"))
            self.assertTrue(self_audit["stress_metric_scope_check"])
            self.assertTrue(self_audit["future_field_usage_check"])
            self.assertEqual(
                "ZERO_COST_REFERENCE rolling_5y_average_ending_equity recomputed from normalized rows",
                self_audit["baseline_metric_used"],
            )

    def test_missing_artifacts_block_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            output_root = package_root / "output"
            output_root.mkdir(parents=True, exist_ok=True)
            result = write_execution_cost_realism_and_trade_redundancy_audit(
                ExecutionCostRealismAndTradeRedundancyAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "execution_cost_realism_and_trade_redundancy_audit_001",
                    random_repeat_count=8,
                )
            )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("EXECUTION_COST_REALISM_AND_TRADE_REDUNDANCY_AUDIT_BLOCKED", summary["final_classification"])
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])

    def test_timestamp_fallback_uses_timestamp_when_exit_missing(self) -> None:
        rows = [
            {
                "trade_id": "A",
                "timestamp": "2024-01-15T12:00:00Z",
                "applied_r": "1.5",
                "risk_multiplier": "1.25",
            },
            {
                "trade_id": "B",
                "entry_timestamp": "2024-02-20T09:00:00Z",
                "r_multiple": "2.0",
            },
        ]
        normalized, schema_info, warnings, errors = _normalize_rows_for_audit(rows)
        self.assertFalse(errors)
        self.assertEqual("timestamp", schema_info["timestamp_field_used"])
        self.assertEqual("2024-01", normalized[0]["exit_timestamp"].strftime("%Y-%m"))
        self.assertEqual("2024-02", normalized[1]["exit_timestamp"].strftime("%Y-%m"))
        self.assertEqual(1.5, normalized[0]["r_multiple"])
        self.assertEqual(2.0, normalized[1]["r_multiple"])
        self.assertTrue(any("applied_r fallback" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()
