import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import structural_compounding_lab.diagnostics.six_hour_native_execution_tide_context_audit as audit_module
from structural_compounding_lab.diagnostics.six_hour_native_execution_tide_context_audit import (
    SixHourNativeExecutionTideContextAuditConfig,
    write_six_hour_native_execution_tide_context_audit,
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
    source_path = root / "data_storage" / "BTCUSDT" / "1m" / "BTCUSDT_1m_2021-01-01_to_2021-08-31.csv"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    start = datetime(2021, 1, 1, 0, 0, tzinfo=timezone.utc)
    rows: list[dict[str, object]] = []
    price = 30000.0
    for index in range(240 * 24 * 60):
        ts = start + timedelta(minutes=index)
        regime = 6.0 if (index // (24 * 60 * 18)) % 2 == 0 else -4.5
        wave = ((index % 90) - 45) * 0.7
        open_price = price
        close_price = max(1000.0, price + (regime * 0.08) + wave * 0.015)
        high_price = max(open_price, close_price) + 14.0
        low_price = min(open_price, close_price) - 14.0
        volume = 140.0 + (index % 40) * 2.5
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
        json.dumps({"baseline_reconciliation_pass_after_repair": True, "selected_repair_mode": audit_module.EXPECTED_REPAIR_MODE}),
        encoding="utf-8",
    )
    htf_output = output_root / "htf_context_role_reconciliation_audit_001"
    htf_output.mkdir(parents=True, exist_ok=True)
    (htf_output / "htf_context_role_reconciliation_summary.json").write_text(
        json.dumps(
            {
                "final_classification": "SIX_H_CONTEXT_IMPROVES_1H_RESEARCH_ONLY",
                "best_context_variant": "LIGHT_BOOST_6H_CONFLUENCE",
                "best_normal_cost_average": 881465.53,
                "best_normal_cost_median": 878431.05,
                "best_hit_1m_windows": 18,
            }
        ),
        encoding="utf-8",
    )
    (htf_output / "diagnostics").mkdir(parents=True, exist_ok=True)
    (htf_output / "diagnostics" / "six_hour_role_decision.json").write_text(
        json.dumps({"decision": "SIX_H_CONTEXT_IMPROVES_1H_RESEARCH_ONLY"}),
        encoding="utf-8",
    )
    (htf_output / "diagnostics" / "strategic_timeframe_recommendation.json").write_text(
        json.dumps({"next_step": "shadow_forward_validation_of_accepted_1h_engine", "shadow_forward_fallback_recommended": True}),
        encoding="utf-8",
    )
    earned_output = output_root / audit_module.EARNED_GEAR_OUTPUT_FOLDER_NAME
    earned_output.mkdir(parents=True, exist_ok=True)
    (earned_output / "earned_gear_activation_discovery_summary.json").write_text(
        json.dumps({"final_classification": "EARNED_GEAR_DISCOVERY_IMPROVES_BUT_FRAGILE"}),
        encoding="utf-8",
    )
    broad_ledger = output_root / "broad_historical_structural_replay_001" / "ledger"
    broad_ledger.mkdir(parents=True, exist_ok=True)
    (broad_ledger / "summary.json").write_text(json.dumps({"source_csv": str(source_csv)}), encoding="utf-8")


def _synthetic_trade_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    start = pd.Timestamp("2021-02-01T06:00:00")
    for index in range(48):
        entry_ts = start + pd.Timedelta(hours=24 * index)
        exit_ts = entry_ts + pd.Timedelta(hours=2)
        entry_price = 32000.0 + index * 45.0
        side = "long" if index % 2 == 0 else "short"
        stop = entry_price * (0.992 if side == "long" else 1.008)
        r_value = 2.8 if index % 6 in {1, 2, 5} else (-1.0 if index % 5 == 0 else 1.2)
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


class SixHourNativeExecutionTideContextAuditTests(unittest.TestCase):
    def test_full_run_writes_outputs_and_context_timestamps_are_closed(self) -> None:
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
                "timestamp_span_start": "2021-02-01T06:00:00",
                "timestamp_span_end": "2021-03-20T08:00:00",
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
                result = write_six_hour_native_execution_tide_context_audit(
                    SixHourNativeExecutionTideContextAuditConfig(
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
                diagnostics_root / "timeframe_data_coverage.csv",
                diagnostics_root / "resampling_integrity_audit.json",
                diagnostics_root / "six_hour_native_candidate_signals.csv",
                diagnostics_root / "twelve_hour_ocean_context_labels.csv",
                diagnostics_root / "daily_tide_context_labels.csv",
                diagnostics_root / "six_hour_execution_variants.csv",
                diagnostics_root / "six_hour_one_hour_overlap_audit.csv",
                diagnostics_root / "six_hour_over_tightening_audit.csv",
                diagnostics_root / "six_hour_cost_band_results.csv",
                diagnostics_root / "six_hour_rolling_5y_results.csv",
                diagnostics_root / "six_hour_stress_results.csv",
                diagnostics_root / "six_hour_missed_trade_resilience.csv",
                diagnostics_root / "six_hour_scorecard.csv",
                diagnostics_root / "six_hour_native_execution_role_decision.json",
                diagnostics_root / "twelve_hour_ocean_role_decision.json",
                diagnostics_root / "daily_tide_role_decision.json",
                diagnostics_root / "strategic_execution_stack_recommendation.json",
                diagnostics_root / "implementation_self_audit.json",
            ):
                self.assertTrue(path.exists(), str(path))
            with (diagnostics_root / "six_hour_native_candidate_signals.csv").open(encoding="utf-8") as handle:
                candidate_rows = list(csv.DictReader(handle))
            self.assertTrue(candidate_rows)
            first = candidate_rows[0]
            self.assertIn("candidate_families", first)
            with (diagnostics_root / "twelve_hour_ocean_context_labels.csv").open(encoding="utf-8") as handle:
                ocean_rows = list(csv.DictReader(handle))
            with (diagnostics_root / "daily_tide_context_labels.csv").open(encoding="utf-8") as handle:
                tide_rows = list(csv.DictReader(handle))
            self.assertTrue(ocean_rows)
            self.assertTrue(tide_rows)
            ocean = ocean_rows[0]
            tide = tide_rows[0]
            signal_ts = pd.Timestamp(next(row["signal_timestamp"] for row in candidate_rows if row["trade_id"] == ocean["trade_id"]))
            self.assertLessEqual(pd.Timestamp(ocean["twelve_hour_context_candle_close_timestamp"]), signal_ts)
            self.assertLessEqual(pd.Timestamp(tide["daily_context_candle_close_timestamp"]), signal_ts)
            with (diagnostics_root / "six_hour_execution_variants.csv").open(encoding="utf-8") as handle:
                variant_rows = list(csv.DictReader(handle))
            names = {row["variant_name"] for row in variant_rows}
            self.assertIn("SIX_H_NATIVE_NO_CONTEXT", names)
            self.assertIn("ONE_H_BASELINE_PLUS_SIX_H_SCOUT_CAP", names)
            self.assertIn("ONE_H_BASELINE_PLUS_SIX_H_SCOUT_INDEPENDENT_ONLY", names)
            self_audit = json.loads((diagnostics_root / "implementation_self_audit.json").read_text(encoding="utf-8"))
            self.assertFalse(self_audit["twelve_hour_execution_revived"])
            self.assertTrue(self_audit["six_hour_signals_no_future_leakage"])
            self.assertTrue(self_audit["daily_tide_no_future_leakage"])

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
                result = write_six_hour_native_execution_tide_context_audit(
                    SixHourNativeExecutionTideContextAuditConfig(
                        package_root=package_root,
                        output_root=package_root / "output" / audit_module.OUTPUT_FOLDER_NAME,
                        random_repeat_count=32,
                    )
                )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("SIX_H_NATIVE_EXECUTION_REJECTED", summary["final_classification"])

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

            def flaky(spec, candidate_rows, one_h_rows, overlap_map):
                if spec.variant_name == "SIX_H_WITH_12H_OCEAN_ALIGNMENT" and state["calls"] == 0:
                    state["calls"] += 1
                    raise RuntimeError("synthetic interruption")
                return original_apply(spec, candidate_rows, one_h_rows, overlap_map)

            with patch.object(
                audit_module,
                "_load_prior_baseline_anchor_and_stream",
                return_value=(baseline_anchor, _synthetic_trade_rows(), stream_recheck, []),
            ), patch.object(audit_module, "_apply_variant", side_effect=flaky):
                with self.assertRaises(RuntimeError):
                    write_six_hour_native_execution_tide_context_audit(
                        SixHourNativeExecutionTideContextAuditConfig(
                            package_root=package_root,
                            output_root=package_root / "output" / audit_module.OUTPUT_FOLDER_NAME,
                            random_repeat_count=32,
                        )
                    )
            progress = json.loads((package_root / "output" / audit_module.OUTPUT_FOLDER_NAME / "scenario_progress.json").read_text(encoding="utf-8"))
            self.assertIn("SIX_H_NATIVE_NO_CONTEXT", progress["completed_variants"])

            with patch.object(
                audit_module,
                "_load_prior_baseline_anchor_and_stream",
                return_value=(baseline_anchor, _synthetic_trade_rows(), stream_recheck, []),
            ):
                result = write_six_hour_native_execution_tide_context_audit(
                    SixHourNativeExecutionTideContextAuditConfig(
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
