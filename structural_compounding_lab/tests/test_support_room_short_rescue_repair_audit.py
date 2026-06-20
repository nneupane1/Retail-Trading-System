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
from structural_compounding_lab.diagnostics.equal_highs_liquidity_sweep_rescue_forensic_audit import (
    EqualHighsLiquiditySweepRescueForensicAuditConfig,
    write_equal_highs_liquidity_sweep_rescue_forensic_audit,
)
from structural_compounding_lab.diagnostics.rolling_five_year_mission_viability_audit import (
    RollingFiveYearMissionViabilityAuditConfig,
    write_rolling_five_year_mission_viability_audit,
)
from structural_compounding_lab.diagnostics.support_room_short_rescue_repair_audit import (
    SupportRoomShortRescueRepairAuditConfig,
    write_support_room_short_rescue_repair_audit,
)
from structural_compounding_lab.tests.test_broad_frozen_patch_validation import (
    _build_trade_fixture,
    _write_csv,
)


class SupportRoomShortRescueRepairAuditTests(unittest.TestCase):
    def _seed(self, root: Path) -> Path:
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

        write_broad_frozen_patch_validation(BroadFrozenPatchValidationConfig(package_root=package_root, output_root=output_root / "broad_frozen_patch_validation_001"))
        write_broad_patch_bluntness_audit(BroadPatchBluntnessAuditConfig(package_root=package_root, output_root=output_root / "broad_patch_bluntness_audit_001"))
        write_broad_patch_accounting_and_short_rescue_audit(BroadPatchAccountingAndShortRescueAuditConfig(package_root=package_root, output_root=output_root / "broad_patch_accounting_and_short_rescue_audit_001"))
        write_rolling_five_year_mission_viability_audit(RollingFiveYearMissionViabilityAuditConfig(package_root=package_root, output_root=output_root / "rolling_five_year_mission_viability_audit_001"))
        write_equal_highs_liquidity_sweep_rescue_forensic_audit(EqualHighsLiquiditySweepRescueForensicAuditConfig(package_root=package_root, output_root=output_root / "equal_highs_liquidity_sweep_rescue_forensic_audit_001"))
        return package_root

    def test_runs_and_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = self._seed(Path(tmpdir))
            output_root = package_root / "output"
            result = write_support_room_short_rescue_repair_audit(
                SupportRoomShortRescueRepairAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "support_room_short_rescue_repair_audit_001",
                )
            )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertFalse(summary["paper_allowed"])
            self.assertFalse(summary["live_allowed"])
            self.assertFalse(summary["behavior_change_allowed"])
            self.assertIn(summary["final_classification"], {
                "SUPPORT_ROOM_REPAIR_REJECTED",
                "SUPPORT_ROOM_REPAIR_BLOCKED_BY_MISSING_FIELDS",
                "SUPPORT_ROOM_REPAIR_WEAK",
                "SUPPORT_ROOM_REPAIR_IMPROVES_BUT_NOT_MISSION_MOVING",
                "SUPPORT_ROOM_REPAIR_PROMISING_RESEARCH_ONLY",
                "SUPPORT_ROOM_REPAIR_READY_FOR_NATIVE_REPLAY_RESEARCH_ONLY",
            })

            diagnostics_root = output_root / "support_room_short_rescue_repair_audit_001" / "diagnostics"
            self.assertTrue((diagnostics_root / "support_room_damage_summary.json").exists())
            self.assertTrue((diagnostics_root / "sr_field_inventory.json").exists())
            self.assertTrue((diagnostics_root / "missing_sr_fields_for_repair.json").exists())
            self.assertTrue((diagnostics_root / "support_room_threshold_candidates.json").exists())
            self.assertTrue((diagnostics_root / "repaired_support_room_rescue_no_leakage_check.json").exists())

            no_leak = json.loads((diagnostics_root / "repaired_support_room_rescue_no_leakage_check.json").read_text(encoding="utf-8"))
            self.assertTrue(no_leak["final_no_leakage_verdict"])

            with (diagnostics_root / "support_room_damage_reconstruction.csv").open("r", encoding="utf-8") as handle:
                list(csv.DictReader(handle))
            with (diagnostics_root / "support_room_feature_separation.csv").open("r", encoding="utf-8") as handle:
                list(csv.DictReader(handle))
            with (diagnostics_root / "derived_support_room_features.csv").open("r", encoding="utf-8") as handle:
                list(csv.DictReader(handle))
            with (diagnostics_root / "repaired_support_room_rescue_variant_results.csv").open("r", encoding="utf-8") as handle:
                self.assertTrue(list(csv.DictReader(handle)))
            with (diagnostics_root / "repaired_rescue_rolling_5y_results.csv").open("r", encoding="utf-8") as handle:
                self.assertTrue(list(csv.DictReader(handle)))

    def test_missing_artifacts_empty_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / "structural_compounding_lab"
            output_root = package_root / "output"
            output_root.mkdir(parents=True, exist_ok=True)
            result = write_support_room_short_rescue_repair_audit(
                SupportRoomShortRescueRepairAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "support_room_short_rescue_repair_audit_001",
                )
            )
            status = json.loads(result["status"].read_text(encoding="utf-8"))
            self.assertEqual("empty", status["state"])


if __name__ == "__main__":
    unittest.main()
