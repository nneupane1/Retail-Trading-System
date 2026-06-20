import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import structural_compounding_lab.diagnostics.milestone_gated_explosive_compounding_audit as audit_module
from structural_compounding_lab.diagnostics.milestone_gated_explosive_compounding_audit import (
    MilestoneGatedExplosiveCompoundingAuditConfig,
    _normalize_trade_stream,
    _simulate_variant_sequence,
    _variant_specs,
    write_milestone_gated_explosive_compounding_audit,
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


def _synthetic_context_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    start = datetime(2018, 1, 31, 12, 0, tzinfo=timezone.utc)
    for index in range(140):
        exit_ts = start + timedelta(days=14 * index)
        entry_ts = exit_ts - timedelta(hours=4)
        if 100 <= index <= 108:
            applied_r = -2.2
        elif 120 <= index <= 124:
            applied_r = -1.8
        else:
            applied_r = 5.0 if index % 5 not in {0} else 2.5
        entry_price = 10_000.0 + index * 10.0
        side = "long" if index % 2 == 0 else "short"
        stop = entry_price * (0.99 if side == "long" else 1.01)
        exit_price = entry_price + (entry_price - stop) * applied_r if side == "long" else entry_price - (stop - entry_price) * applied_r
        rows.append(
            {
                "trade_id": f"strict-{index}",
                "exit_timestamp": exit_ts.isoformat(),
                "timestamp": exit_ts.isoformat(),
                "entry_timestamp": entry_ts.isoformat(),
                "entry_price": round(entry_price, 6),
                "exit_price": round(exit_price, 6),
                "initial_stop": round(stop, 6),
                "quantity": 1.0,
                "r_multiple": round(applied_r, 6),
                "applied_r": round(applied_r, 6),
                "asset": "BTCUSDT",
                "symbol": "BTCUSDT",
                "side": side,
                "convexity_label": "elite_convexity" if index % 5 == 0 else "strong_convexity",
                "moonshot_state": "moonshot" if index % 9 == 0 else "normal",
                "setup_class": "A+" if index % 7 == 0 else "A",
                "runner_label": "moonshot_runner" if index % 11 == 0 else "normal",
                "archetype_key": "strict_core",
            }
        )
    return rows


def _alternate_field_rows() -> list[dict[str, object]]:
    rows = _synthetic_context_rows()
    remapped: list[dict[str, object]] = []
    for row in rows:
        item = dict(row)
        item.pop("exit_timestamp", None)
        item.pop("r_multiple", None)
        remapped.append(item)
    return remapped


def _seed_fixture(root: Path) -> tuple[Path, list[dict[str, object]]]:
    package_root = root / "structural_compounding_lab"
    output_root = package_root / "output"
    output_root.mkdir(parents=True, exist_ok=True)
    rows = _synthetic_context_rows()
    normalized_rows, _schema, _warnings, _errors = _normalize_trade_stream(rows)
    rolling = audit_module._overlay_rolling_window_summary(
        normalized_rows,
        audit_module._build_windows(normalized_rows),
        {"stepup_schedule": list(audit_module.BASE_STEPUP_SCHEDULE), "cost_bps_total": audit_module.NORMAL_COST_BPS},
    )
    _write_csv(
        output_root / "execution_cost_realism_and_trade_redundancy_audit_001" / "diagnostics" / "execution_cost_band_results.csv",
        [
            {
                "band_name": "NORMAL_MIXED_MAKER_TAKER_COST",
                "rolling_5y_average_ending_equity": rolling["average"],
                "rolling_5y_median_ending_equity": rolling["median"],
                "hit_1m_windows": rolling["hit_1m_windows"],
                "hit_3m_windows": rolling["hit_3m_windows"],
                "hit_5m_windows": rolling["hit_5m_windows"],
            }
        ],
    )
    repair_path = output_root / "native_12h_execution_sleeve_discovery_audit_001" / "diagnostics" / "12h_baseline_accounting_repair_diagnostics.json"
    repair_path.parent.mkdir(parents=True, exist_ok=True)
    repair_path.write_text(
        json.dumps(
            {
                "baseline_reconciliation_pass_after_repair": True,
                "selected_repair_mode": audit_module.EXPECTED_REPAIR_MODE,
            }
        ),
        encoding="utf-8",
    )
    return package_root, rows


class MilestoneGatedExplosiveCompoundingAuditTests(unittest.TestCase):
    def test_baseline_and_reconstruction_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root, rows = _seed_fixture(Path(tmpdir))
            context = {"rows": rows}
            with patch.object(audit_module, "_load_execution_cost_context", return_value=(context, [], {})):
                baseline_anchor, normalized_rows, reconstruction, warnings = audit_module._load_baseline_anchor_and_stream(
                    MilestoneGatedExplosiveCompoundingAuditConfig(
                        package_root=package_root,
                        output_root=package_root / "output" / "milestone_gated_explosive_compounding_audit_001",
                    )
                )
            self.assertFalse(warnings)
            self.assertTrue(baseline_anchor["baseline_reproduction_pass"])
            self.assertTrue(reconstruction["trusted_baseline_reproduced"])
            self.assertEqual("exit_timestamp", reconstruction["timestamp_field_used"])
            self.assertEqual("r_multiple", reconstruction["r_field_used"])
            self.assertTrue(len(normalized_rows) > 100)

    def test_alternate_timestamp_and_r_field_fallback_still_reconstructs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root, _rows = _seed_fixture(Path(tmpdir))
            fallback_rows = _alternate_field_rows()
            normalized_rows, schema, warnings, errors = _normalize_trade_stream(fallback_rows)
            self.assertFalse(errors)
            self.assertTrue(any("R fallback used from applied_r" in warning for warning in warnings))
            self.assertEqual("timestamp", schema["timestamp_field_used"])
            context = {"rows": fallback_rows}
            with patch.object(audit_module, "_load_execution_cost_context", return_value=(context, [], {})):
                baseline_anchor, normalized_from_loader, reconstruction, loader_warnings = audit_module._load_baseline_anchor_and_stream(
                    MilestoneGatedExplosiveCompoundingAuditConfig(
                        package_root=package_root,
                        output_root=package_root / "output" / "milestone_gated_explosive_compounding_audit_001",
                    )
                )
            self.assertTrue(baseline_anchor["baseline_reproduction_pass"])
            self.assertEqual("timestamp", reconstruction["timestamp_field_used"])
            self.assertEqual("applied_r", reconstruction["r_field_used"])
            self.assertEqual(len(normalized_rows), len(normalized_from_loader))
            self.assertTrue(any("R fallback used from applied_r" in warning for warning in loader_warnings))

    def test_variants_capped_and_moonshot_variant_available(self) -> None:
        specs = _variant_specs(_synthetic_context_rows())
        self.assertLessEqual(len(specs), audit_module.MAX_VARIANTS)
        moonshot = next(spec for spec in specs if spec.variant_name == "GEAR_AFTER_300K_WITH_MOONSHOT_ONLY_BOOST")
        self.assertTrue(moonshot.available)

    def test_300k_activation_drawdown_stepdown_and_vault_accounting(self) -> None:
        normalized_rows, _schema, _warnings, _errors = _normalize_trade_stream(_synthetic_context_rows())
        specs = {spec.variant_name: spec for spec in _variant_specs(_synthetic_context_rows())}
        baseline = _simulate_variant_sequence(normalized_rows, specs["BASELINE_REPAIRED_1H"], cost_bps_total=audit_module.NORMAL_COST_BPS)
        boosted = _simulate_variant_sequence(normalized_rows, specs["GEAR_AFTER_300K_WITH_DRAWDOWN_STEPDOWN"], cost_bps_total=audit_module.NORMAL_COST_BPS)
        vaulted = _simulate_variant_sequence(normalized_rows, specs["GEAR_AFTER_300K_WITH_PROFIT_VAULT"], cost_bps_total=audit_module.NORMAL_COST_BPS)
        self.assertGreater(boosted["gear_activations"], 0)
        self.assertGreater(boosted["gear_down_events"], 0)
        self.assertGreaterEqual(boosted["risk_multiplier_max"], baseline["risk_multiplier_max"])
        self.assertAlmostEqual(vaulted["ending_equity"], vaulted["active_equity"] + vaulted["locked_profit"], places=5)
        self.assertGreaterEqual(vaulted["locked_profit"], 0.0)

    def test_full_run_writes_outputs_and_scout_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root, rows = _seed_fixture(Path(tmpdir))
            output_root = package_root / "output" / "milestone_gated_explosive_compounding_audit_001"
            context = {"rows": rows}
            with patch.object(audit_module, "_load_execution_cost_context", return_value=(context, [], {})):
                result = write_milestone_gated_explosive_compounding_audit(
                    MilestoneGatedExplosiveCompoundingAuditConfig(
                        package_root=package_root,
                        output_root=output_root,
                        random_repeat_count=8,
                    )
                )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertFalse(summary["paper_allowed"])
            self.assertFalse(summary["live_allowed"])
            self.assertFalse(summary["behavior_change_allowed"])
            self.assertTrue(summary["scout_mode"])
            self.assertEqual("resume_capable", summary["checkpoint_resume_status"])
            self.assertIn(
                summary["final_classification"],
                {
                    "MILESTONE_GATED_COMPOUNDING_REJECTED",
                    "MILESTONE_GATED_COMPOUNDING_WEAK",
                    "MILESTONE_GATED_COMPOUNDING_IMPROVES_BUT_FRAGILE",
                    "MILESTONE_GATED_COMPOUNDING_1M_PROMISING_RESEARCH_ONLY",
                    "MILESTONE_GATED_COMPOUNDING_3M_PROMISING_RESEARCH_ONLY",
                    "MILESTONE_GATED_COMPOUNDING_READY_FOR_FREEZE_AND_CONFIRM_RESEARCH_ONLY",
                    "MILESTONE_GATED_COMPOUNDING_NO_IMPROVEMENT_MOVE_TO_SHADOW_SPEC",
                },
            )
            diagnostics_root = output_root / "diagnostics"
            ledger_root = output_root / "ledger"
            checkpoints_root = output_root / "_checkpoints"
            for path in (
                diagnostics_root / "baseline_anchor.json",
                diagnostics_root / "trusted_1h_trade_stream_reconstruction.json",
                diagnostics_root / "milestone_capital_gear_variants.csv",
                diagnostics_root / "milestone_capital_gear_variant_specs.json",
                diagnostics_root / "milestone_gated_cost_band_results.csv",
                diagnostics_root / "milestone_gated_rolling_5y_results.csv",
                diagnostics_root / "milestone_gated_fragility_results.csv",
                diagnostics_root / "milestone_gated_missed_trade_resilience.csv",
                diagnostics_root / "stochastic_budget_reliability_check.json",
                diagnostics_root / "mission_target_interpretation.json",
                diagnostics_root / "freeze_and_confirm_candidate.json",
                diagnostics_root / "implementation_self_audit.json",
                diagnostics_root / "run_progress.json",
                ledger_root / "milestone_gated_equity_curves.csv",
                ledger_root / "milestone_gated_trade_ledgers.csv",
                output_root / "scenario_progress.json",
                output_root / "status.json",
                checkpoints_root / "checkpoint_index.json",
            ):
                self.assertTrue(path.exists(), str(path))
            self_audit = json.loads((diagnostics_root / "implementation_self_audit.json").read_text(encoding="utf-8"))
            self.assertTrue(self_audit["gear_activation_not_future_leaking"])
            self.assertTrue(self_audit["drawdown_brake_check"])
            self.assertTrue(self_audit["profit_vault_check"])
            self.assertTrue(self_audit["parameter_grid_overfit_check"])
            stochastic = json.loads((diagnostics_root / "stochastic_budget_reliability_check.json").read_text(encoding="utf-8"))
            self.assertTrue(stochastic["scout_mode"])
            self.assertFalse(stochastic["stochastic_results_reliable_for_final_gate"])

    def test_interrupted_run_can_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root, rows = _seed_fixture(Path(tmpdir))
            output_root = package_root / "output" / "milestone_gated_explosive_compounding_audit_001"
            context = {"rows": rows}
            original_simulate = audit_module._simulate_variant_sequence
            state = {"calls": 0}

            def flaky(rows_arg, spec_arg, *, cost_bps_total):
                if spec_arg.variant_name == "GEAR_AFTER_300K_LIGHT" and cost_bps_total == audit_module.ZERO_COST_BPS and state["calls"] == 0:
                    state["calls"] += 1
                    raise RuntimeError("synthetic interruption")
                return original_simulate(rows_arg, spec_arg, cost_bps_total=cost_bps_total)

            with patch.object(audit_module, "_load_execution_cost_context", return_value=(context, [], {})), patch.object(
                audit_module, "_simulate_variant_sequence", side_effect=flaky
            ):
                with self.assertRaises(RuntimeError):
                    write_milestone_gated_explosive_compounding_audit(
                        MilestoneGatedExplosiveCompoundingAuditConfig(
                            package_root=package_root,
                            output_root=output_root,
                            random_repeat_count=8,
                        )
                    )

            progress = json.loads((output_root / "scenario_progress.json").read_text(encoding="utf-8"))
            self.assertIn("BASELINE_REPAIRED_1H", progress["completed_variants"])

            with patch.object(audit_module, "_load_execution_cost_context", return_value=(context, [], {})):
                result = write_milestone_gated_explosive_compounding_audit(
                    MilestoneGatedExplosiveCompoundingAuditConfig(
                        package_root=package_root,
                        output_root=output_root,
                        random_repeat_count=8,
                    )
                )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertTrue(summary["checkpoint_resume_status"] == "resume_capable")
            final_progress = json.loads((output_root / "scenario_progress.json").read_text(encoding="utf-8"))
            self.assertEqual("completed", final_progress["state"])
            self.assertGreaterEqual(len(final_progress["completed_variants"]), 8)


if __name__ == "__main__":
    unittest.main()
