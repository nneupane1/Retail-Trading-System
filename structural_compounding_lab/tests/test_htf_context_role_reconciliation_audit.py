import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import structural_compounding_lab.diagnostics.htf_context_role_reconciliation_audit as audit_module
from structural_compounding_lab.diagnostics.htf_context_role_reconciliation_audit import (
    HTFContextRoleReconciliationAuditConfig,
    write_htf_context_role_reconciliation_audit,
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


def _seed_source_csv(root: Path) -> Path:
    source_path = root / "data_storage" / "BTCUSDT" / "1m" / "BTCUSDT_1m_2021-01-01_to_2021-01-10.csv"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    start = datetime(2021, 1, 1, 0, 0, tzinfo=timezone.utc)
    rows: list[dict[str, object]] = []
    price = 30000.0
    for index in range(10 * 24 * 60):
        ts = start + timedelta(minutes=index)
        drift = 2.0 if (index // 240) % 2 == 0 else -1.2
        wave = ((index % 45) - 22) * 0.8
        open_price = price
        close_price = max(1000.0, price + drift + wave * 0.05)
        high_price = max(open_price, close_price) + 8.0
        low_price = min(open_price, close_price) - 8.0
        volume = 100.0 + (index % 20) * 3.0
        rows.append(
            {
                "timestamp": ts.isoformat(),
                "open": round(open_price, 6),
                "high": round(high_price, 6),
                "low": round(low_price, 6),
                "close": round(close_price, 6),
                "volume": round(volume, 6),
            }
        )
        price = close_price
    _write_csv(source_path, rows)
    return source_path


def _seed_prior_artifacts(package_root: Path, source_csv: Path) -> None:
    output_root = package_root / "output"
    _write_csv(
        output_root / "execution_cost_realism_and_trade_redundancy_audit_001" / "diagnostics" / "execution_cost_band_results.csv",
        [
            {
                "band_name": "NORMAL_MIXED_MAKER_TAKER_COST",
                "rolling_5y_average_ending_equity": 792824.56,
                "rolling_5y_median_ending_equity": 786049.45,
                "hit_1m_windows": 12,
                "hit_3m_windows": 2,
                "hit_5m_windows": 0,
            }
        ],
    )
    twelve_h_output = output_root / "native_12h_execution_sleeve_discovery_audit_001"
    twelve_h_output.mkdir(parents=True, exist_ok=True)
    (twelve_h_output / "native_12h_execution_sleeve_discovery_summary.json").write_text(
        json.dumps({"final_classification": "NATIVE_12H_EXECUTION_REJECTED"}),
        encoding="utf-8",
    )
    (twelve_h_output / "diagnostics").mkdir(parents=True, exist_ok=True)
    (twelve_h_output / "diagnostics" / "12h_baseline_accounting_repair_diagnostics.json").write_text(
        json.dumps(
            {
                "baseline_reconciliation_pass_after_repair": True,
                "selected_repair_mode": audit_module.EXPECTED_REPAIR_MODE,
            }
        ),
        encoding="utf-8",
    )
    earned_output = output_root / audit_module.EARNED_GEAR_OUTPUT_FOLDER_NAME
    earned_output.mkdir(parents=True, exist_ok=True)
    (earned_output / "earned_gear_activation_discovery_summary.json").write_text(
        json.dumps(
            {
                "final_classification": "EARNED_GEAR_DISCOVERY_IMPROVES_BUT_FRAGILE",
                "best_variant": "AGGRESSIVE_CONTROLLED_REFERENCE_300K",
            }
        ),
        encoding="utf-8",
    )
    (earned_output / "reports").mkdir(parents=True, exist_ok=True)
    (earned_output / "reports" / "next_research_recommendation.json").write_text(
        json.dumps({"next_step": "shadow_forward_validation", "shadow_only": True}),
        encoding="utf-8",
    )
    broad_ledger = output_root / "broad_historical_structural_replay_001" / "ledger"
    broad_ledger.mkdir(parents=True, exist_ok=True)
    (broad_ledger / "summary.json").write_text(json.dumps({"source_csv": str(source_csv)}), encoding="utf-8")


def _synthetic_trade_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    start = pd.Timestamp("2021-01-03T06:00:00")
    for index in range(24):
        entry_ts = start + pd.Timedelta(hours=6 * index)
        exit_ts = entry_ts + pd.Timedelta(hours=1)
        entry_price = 30200.0 + index * 35.0
        side = "long" if index % 2 == 0 else "short"
        stop = entry_price * (0.992 if side == "long" else 1.008)
        r_value = 3.2 if index % 5 in {1, 2, 4} else (-1.0 if index % 4 == 0 else 1.4)
        exit_price = entry_price + abs(entry_price - stop) * r_value if side == "long" else entry_price - abs(entry_price - stop) * r_value
        rows.append(
            {
                "trade_id": f"strict-{index}",
                "entry_timestamp": entry_ts,
                "exit_timestamp": exit_ts,
                "timestamp": exit_ts,
                "entry_price": round(entry_price, 6),
                "exit_price": round(exit_price, 6),
                "initial_stop": round(stop, 6),
                "quantity": 1.0,
                "r_multiple": round(r_value, 6),
                "side": side,
                "symbol": "BTCUSDT",
                "archetype_key": "strict_core",
            }
        )
    return rows


class HTFContextRoleReconciliationAuditTests(unittest.TestCase):
    def test_full_run_writes_outputs_and_uses_closed_context_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            source_csv = _seed_source_csv(Path(tmpdir))
            _seed_prior_artifacts(package_root, source_csv)
            baseline_anchor = {
                "rolling_5y_average_ending_equity": 792824.56,
                "rolling_5y_median_ending_equity": 786049.45,
                "hit_1m_windows": 12,
            }
            stream_recheck = {
                "trusted_baseline_reproduced": True,
                "expected_row_count_near_558": False,
                "timestamp_span_start": "2021-01-03T07:00:00",
                "timestamp_span_end": "2021-01-09T19:00:00",
                "timestamp_field_used": "exit_timestamp",
                "r_field_used": "r_multiple",
                "cost_model_used": "execution_cost_overlay_sequence_with_profit_locking",
                "synthetic_stop_distance_cost_model_used": False,
                "schema_fields_detected": ["entry_timestamp", "exit_timestamp", "r_multiple"],
            }
            with patch.object(
                audit_module,
                "_load_prior_baseline_anchor_and_stream",
                return_value=(baseline_anchor, _synthetic_trade_rows(), stream_recheck, []),
            ):
                result = write_htf_context_role_reconciliation_audit(
                    HTFContextRoleReconciliationAuditConfig(
                        package_root=package_root,
                        output_root=package_root / "output" / audit_module.OUTPUT_FOLDER_NAME,
                        random_repeat_count=32,
                    )
                )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertFalse(summary["paper_allowed"])
            self.assertFalse(summary["live_allowed"])
            self.assertFalse(summary["behavior_change_allowed"])
            diagnostics_root = package_root / "output" / audit_module.OUTPUT_FOLDER_NAME / "diagnostics"
            for path in (
                diagnostics_root / "prior_court_anchor.json",
                diagnostics_root / "trusted_1h_trade_stream_recheck.json",
                diagnostics_root / "timeframe_data_coverage.csv",
                diagnostics_root / "timeframe_resampling_audit.json",
                diagnostics_root / "htf_context_labels.csv",
                diagnostics_root / "ltf_15m_refinement_labels.csv",
                diagnostics_root / "context_label_schema.json",
                diagnostics_root / "context_bucket_performance.csv",
                diagnostics_root / "context_overlay_variant_specs.json",
                diagnostics_root / "context_overlay_variants.csv",
                diagnostics_root / "over_tightening_audit.csv",
                diagnostics_root / "htf_context_cost_band_results.csv",
                diagnostics_root / "htf_context_rolling_5y_results.csv",
                diagnostics_root / "htf_context_stress_results.csv",
                diagnostics_root / "htf_context_missed_trade_resilience.csv",
                diagnostics_root / "six_hour_role_decision.json",
                diagnostics_root / "twelve_hour_role_decision.json",
                diagnostics_root / "strategic_timeframe_recommendation.json",
                diagnostics_root / "implementation_self_audit.json",
            ):
                self.assertTrue(path.exists(), str(path))
            with (diagnostics_root / "htf_context_labels.csv").open(encoding="utf-8") as handle:
                label_rows = list(csv.DictReader(handle))
            self.assertTrue(label_rows)
            first = label_rows[0]
            self.assertIn("4h_supply_price", first)
            self.assertIn("6h_room_to_target_r", first)
            self.assertIn("12h_conflict", first)
            entry_ts = pd.Timestamp(first["entry_timestamp"])
            self.assertLessEqual(pd.Timestamp(first["4h_context_candle_close_timestamp"]), entry_ts)
            self.assertLessEqual(pd.Timestamp(first["6h_context_candle_close_timestamp"]), entry_ts)
            self.assertLessEqual(pd.Timestamp(first["12h_context_candle_close_timestamp"]), entry_ts)
            specs = json.loads((diagnostics_root / "context_overlay_variant_specs.json").read_text(encoding="utf-8"))
            names = {item["variant_name"] for item in specs["variants"]}
            self.assertIn("FILTER_6H_TREND_ALIGNED", names)
            self.assertIn("FILTER_12H_CONTEXT_ALIGNED_DIAGNOSTIC_ONLY", names)
            self.assertIn("SIX_H_NATIVE_EXECUTION_SCOUT", names)

    def test_missing_source_blocks_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            _seed_prior_artifacts(package_root, Path(tmpdir) / "does_not_exist.csv")
            baseline_anchor = {
                "rolling_5y_average_ending_equity": 792824.56,
                "rolling_5y_median_ending_equity": 786049.45,
                "hit_1m_windows": 12,
            }
            stream_recheck = {
                "trusted_baseline_reproduced": True,
                "timestamp_field_used": "exit_timestamp",
                "r_field_used": "r_multiple",
                "cost_model_used": "execution_cost_overlay_sequence_with_profit_locking",
                "synthetic_stop_distance_cost_model_used": False,
                "schema_fields_detected": ["entry_timestamp", "exit_timestamp", "r_multiple"],
            }
            with patch.object(
                audit_module,
                "_load_prior_baseline_anchor_and_stream",
                return_value=(baseline_anchor, _synthetic_trade_rows(), stream_recheck, []),
            ):
                result = write_htf_context_role_reconciliation_audit(
                    HTFContextRoleReconciliationAuditConfig(
                        package_root=package_root,
                        output_root=package_root / "output" / audit_module.OUTPUT_FOLDER_NAME,
                        random_repeat_count=32,
                    )
                )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("HTF_CONTEXT_REJECTED", summary["final_classification"])

    def test_interrupted_run_can_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            source_csv = _seed_source_csv(Path(tmpdir))
            _seed_prior_artifacts(package_root, source_csv)
            baseline_anchor = {
                "rolling_5y_average_ending_equity": 792824.56,
                "rolling_5y_median_ending_equity": 786049.45,
                "hit_1m_windows": 12,
            }
            stream_recheck = {
                "trusted_baseline_reproduced": True,
                "timestamp_field_used": "exit_timestamp",
                "r_field_used": "r_multiple",
                "cost_model_used": "execution_cost_overlay_sequence_with_profit_locking",
                "synthetic_stop_distance_cost_model_used": False,
                "schema_fields_detected": ["entry_timestamp", "exit_timestamp", "r_multiple"],
            }
            state = {"calls": 0}
            original_apply = audit_module._apply_variant

            def flaky(spec, rows, label_map):
                if spec.variant_name == "FILTER_6H_TREND_ALIGNED" and state["calls"] == 0:
                    state["calls"] += 1
                    raise RuntimeError("synthetic interruption")
                return original_apply(spec, rows, label_map)

            with patch.object(
                audit_module,
                "_load_prior_baseline_anchor_and_stream",
                return_value=(baseline_anchor, _synthetic_trade_rows(), stream_recheck, []),
            ), patch.object(audit_module, "_apply_variant", side_effect=flaky):
                with self.assertRaises(RuntimeError):
                    write_htf_context_role_reconciliation_audit(
                        HTFContextRoleReconciliationAuditConfig(
                            package_root=package_root,
                            output_root=package_root / "output" / audit_module.OUTPUT_FOLDER_NAME,
                            random_repeat_count=32,
                        )
                    )
            progress = json.loads((package_root / "output" / audit_module.OUTPUT_FOLDER_NAME / "scenario_progress.json").read_text(encoding="utf-8"))
            self.assertIn("BASELINE_1H_REPAIRED", progress["completed_variants"])

            with patch.object(
                audit_module,
                "_load_prior_baseline_anchor_and_stream",
                return_value=(baseline_anchor, _synthetic_trade_rows(), stream_recheck, []),
            ):
                result = write_htf_context_role_reconciliation_audit(
                    HTFContextRoleReconciliationAuditConfig(
                        package_root=package_root,
                        output_root=package_root / "output" / audit_module.OUTPUT_FOLDER_NAME,
                        random_repeat_count=32,
                    )
                )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("resume_capable", summary["checkpoint_resume_status"])
            final_progress = json.loads((package_root / "output" / audit_module.OUTPUT_FOLDER_NAME / "scenario_progress.json").read_text(encoding="utf-8"))
            self.assertEqual("completed", final_progress["state"])


if __name__ == "__main__":
    unittest.main()
