import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import structural_compounding_lab.diagnostics.milestone_gated_compounding_fragility_repair_audit as repair_module
import structural_compounding_lab.diagnostics.milestone_gated_explosive_compounding_audit as prior_audit_module
from structural_compounding_lab.diagnostics.milestone_bridge_fragility_driver_repair_audit import (
    BASE_STEPUP_SCHEDULE,
    _rolling_window_summary,
)
from structural_compounding_lab.diagnostics.milestone_gated_compounding_fragility_repair_audit import (
    MilestoneGatedCompoundingFragilityRepairAuditConfig,
    _scorecard,
    _trusted_stream_recheck,
    _variant_specs,
    write_milestone_gated_compounding_fragility_repair_audit,
)
from structural_compounding_lab.diagnostics.milestone_gated_explosive_compounding_audit import (
    MilestoneGatedExplosiveCompoundingAuditConfig,
    _normalize_trade_stream,
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
            volatility_score = 0.93
        elif 120 <= index <= 124:
            applied_r = -1.8
            volatility_score = 0.88
        else:
            applied_r = 5.0 if index % 5 not in {0} else 2.5
            volatility_score = 0.35 if index % 6 else 0.78
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
                "volatility_score": volatility_score,
                "danger_score": volatility_score,
            }
        )
    return rows


def _seed_execution_cost_fixture(root: Path, rows: list[dict[str, object]]) -> Path:
    package_root = root / "structural_compounding_lab"
    output_root = package_root / "output"
    output_root.mkdir(parents=True, exist_ok=True)
    normalized_rows, _schema, _warnings, _errors = _normalize_trade_stream(rows)
    rolling = _rolling_window_summary(
        normalized_rows,
        repair_module._build_windows(normalized_rows),
        {"stepup_schedule": list(BASE_STEPUP_SCHEDULE), "cost_bps_total": repair_module.NORMAL_COST_BPS},
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
                "selected_repair_mode": repair_module.EXPECTED_REPAIR_MODE,
            }
        ),
        encoding="utf-8",
    )
    return package_root


def _seed_prior_milestone_output(root: Path) -> tuple[Path, list[dict[str, object]]]:
    rows = _synthetic_context_rows()
    package_root = _seed_execution_cost_fixture(root, rows)
    context = {"rows": rows}
    with patch.object(prior_audit_module, "_load_execution_cost_context", return_value=(context, [], {})):
        write_milestone_gated_explosive_compounding_audit(
            MilestoneGatedExplosiveCompoundingAuditConfig(
                package_root=package_root,
                output_root=package_root / "output" / "milestone_gated_explosive_compounding_audit_001",
                random_repeat_count=8,
            )
        )
    return package_root, rows


class MilestoneGatedCompoundingFragilityRepairAuditTests(unittest.TestCase):
    def test_prior_anchor_and_stream_recheck_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root, rows = _seed_prior_milestone_output(Path(tmpdir))
            prior_anchor, _cost_rows, _fragility_rows, warnings = repair_module._load_prior_milestone_anchor(
                MilestoneGatedCompoundingFragilityRepairAuditConfig(
                    package_root=package_root,
                    output_root=package_root / "output" / "milestone_gated_compounding_fragility_repair_audit_001",
                )
            )
            self.assertFalse(warnings)
            self.assertTrue(prior_anchor["baseline_anchor_match"])
            context = {"rows": rows}
            with patch.object(prior_audit_module, "_load_execution_cost_context", return_value=(context, [], {})):
                stream_recheck, normalized_rows, stream_warnings = _trusted_stream_recheck(
                    MilestoneGatedCompoundingFragilityRepairAuditConfig(
                        package_root=package_root,
                        output_root=package_root / "output" / "milestone_gated_compounding_fragility_repair_audit_001",
                    )
                )
            self.assertFalse(stream_warnings)
            self.assertTrue(stream_recheck["trusted_baseline_reproduced"])
            self.assertEqual("exit_timestamp", stream_recheck["timestamp_field_used"])
            self.assertEqual("r_multiple", stream_recheck["r_field_used"])
            self.assertTrue(len(normalized_rows) > 100)

    def test_variants_generated_and_capped_and_prior_best_present(self) -> None:
        specs = _variant_specs(_synthetic_context_rows())
        self.assertLessEqual(len(specs), repair_module.MAX_VARIANTS)
        names = {spec.variant_name for spec in specs}
        self.assertIn("PRIOR_BEST_REPLAY", names)
        self.assertIn("GEAR_AFTER_300K_WITH_VOLATILITY_BRAKE", names)

    def test_drawdown_stepdown_and_vault_protection_no_doublecount(self) -> None:
        normalized_rows, _schema, _warnings, _errors = _normalize_trade_stream(_synthetic_context_rows())
        specs = {spec.variant_name: spec for spec in _variant_specs(_synthetic_context_rows())}
        stepped = repair_module._simulate_repair_variant_sequence(
            normalized_rows,
            specs["GEAR_AFTER_300K_BALANCED_WITH_DRAWDOWN_STEPDOWN"],
            cost_bps_total=repair_module.NORMAL_COST_BPS,
        )
        vaulted = repair_module._simulate_repair_variant_sequence(
            normalized_rows,
            specs["GEAR_AFTER_300K_WITH_STRONGER_PROFIT_VAULT"],
            cost_bps_total=repair_module.NORMAL_COST_BPS,
        )
        self.assertGreater(stepped["gear_activations"], 0)
        self.assertGreater(stepped["gear_down_events"], 0)
        self.assertAlmostEqual(vaulted["ending_equity"], vaulted["active_equity"] + vaulted["locked_profit"], places=5)
        self.assertGreaterEqual(vaulted["locked_profit"], 0.0)

    def test_full_run_writes_outputs_scorecard_and_shadow_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root, rows = _seed_prior_milestone_output(Path(tmpdir))
            output_root = package_root / "output" / "milestone_gated_compounding_fragility_repair_audit_001"
            context = {"rows": rows}
            with patch.object(prior_audit_module, "_load_execution_cost_context", return_value=(context, [], {})):
                result = write_milestone_gated_compounding_fragility_repair_audit(
                    MilestoneGatedCompoundingFragilityRepairAuditConfig(
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
            self.assertEqual("resume_capable", summary["checkpoint_resume_status"])
            diagnostics_root = output_root / "diagnostics"
            for path in (
                diagnostics_root / "prior_milestone_audit_anchor.json",
                diagnostics_root / "trusted_1h_stream_recheck.json",
                diagnostics_root / "fragility_repair_variant_specs.json",
                diagnostics_root / "fragility_repair_cost_band_results.csv",
                diagnostics_root / "fragility_repair_stress_results.csv",
                diagnostics_root / "fragility_repair_missed_trade_resilience.csv",
                diagnostics_root / "fragility_repair_scorecard.csv",
                diagnostics_root / "best_repaired_variant_selection.json",
                diagnostics_root / "shadow_fallback_decision.json",
                diagnostics_root / "implementation_self_audit.json",
                diagnostics_root / "stochastic_budget_reliability_check.json",
                diagnostics_root / "run_progress.json",
                output_root / "scenario_progress.json",
                output_root / "status.json",
                output_root / "_checkpoints" / "checkpoint_index.json",
            ):
                self.assertTrue(path.exists(), str(path))
            with (diagnostics_root / "fragility_repair_scorecard.csv").open(encoding="utf-8") as handle:
                scorecard_rows = list(csv.DictReader(handle))
            self.assertTrue(any(row["variant_name"] == "PRIOR_BEST_REPLAY" for row in scorecard_rows))
            with (diagnostics_root / "fragility_repair_stress_results.csv").open(encoding="utf-8") as handle:
                stress_rows = list(csv.DictReader(handle))
            self.assertTrue(any(row["scenario"] == "remove_top_5_winners" for row in stress_rows))
            self.assertTrue(any(row["scenario"] == "r_haircut_20pct" for row in stress_rows))

    def test_interrupted_run_can_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root, rows = _seed_prior_milestone_output(Path(tmpdir))
            output_root = package_root / "output" / "milestone_gated_compounding_fragility_repair_audit_001"
            context = {"rows": rows}
            original_simulate = repair_module._simulate_repair_variant_sequence
            state = {"calls": 0}

            def flaky(rows_arg, spec_arg, *, cost_bps_total):
                if spec_arg.variant_name == "GEAR_AFTER_300K_BALANCED_REPAIR" and cost_bps_total == repair_module.ZERO_COST_BPS and state["calls"] == 0:
                    state["calls"] += 1
                    raise RuntimeError("synthetic interruption")
                return original_simulate(rows_arg, spec_arg, cost_bps_total=cost_bps_total)

            with patch.object(prior_audit_module, "_load_execution_cost_context", return_value=(context, [], {})), patch.object(
                repair_module, "_simulate_repair_variant_sequence", side_effect=flaky
            ):
                with self.assertRaises(RuntimeError):
                    write_milestone_gated_compounding_fragility_repair_audit(
                        MilestoneGatedCompoundingFragilityRepairAuditConfig(
                            package_root=package_root,
                            output_root=output_root,
                            random_repeat_count=8,
                        )
                    )
            progress = json.loads((output_root / "scenario_progress.json").read_text(encoding="utf-8"))
            self.assertIn("PRIOR_BEST_REPLAY", progress["completed_variants"])

            with patch.object(prior_audit_module, "_load_execution_cost_context", return_value=(context, [], {})):
                result = write_milestone_gated_compounding_fragility_repair_audit(
                    MilestoneGatedCompoundingFragilityRepairAuditConfig(
                        package_root=package_root,
                        output_root=output_root,
                        random_repeat_count=8,
                    )
                )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("resume_capable", summary["checkpoint_resume_status"])
            final_progress = json.loads((output_root / "scenario_progress.json").read_text(encoding="utf-8"))
            self.assertEqual("completed", final_progress["state"])


if __name__ == "__main__":
    unittest.main()
