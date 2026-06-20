import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from structural_compounding_lab.shadow_forward.shadow_forward_observer import (
    DEFAULT_RUNTIME_MODE,
    OUTPUT_FOLDER_NAME,
    ShadowForwardObserverConfig,
    write_shadow_forward_observer,
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


def _seed_shadow_spec(package_root: Path) -> None:
    spec_root = package_root / "output" / "shadow_forward_validation_spec_audit_001"
    (spec_root / "diagnostics").mkdir(parents=True, exist_ok=True)
    _write_csv(
        package_root / "output" / "execution_cost_realism_and_trade_redundancy_audit_001" / "diagnostics" / "execution_cost_band_results.csv",
        [
            {
                "band_name": "NORMAL_MIXED_MAKER_TAKER_COST",
                "total_round_trip_bps": 15.0,
                "rolling_5y_average_ending_equity": 792824.56,
                "rolling_5y_median_ending_equity": 786049.45,
                "hit_1m_windows": 12,
            },
            {
                "band_name": "CONSERVATIVE_TAKER_COST",
                "total_round_trip_bps": 20.0,
            },
            {
                "band_name": "HIGH_SLIPPAGE_COST",
                "total_round_trip_bps": 30.0,
            },
        ],
    )
    (spec_root / "shadow_forward_validation_spec_summary.json").write_text(
        json.dumps(
            {
                "final_classification": "SHADOW_SPEC_READY_WITH_6H_CONTEXT_RESEARCH_ONLY",
                "shadow_observation_duration_recommended_days": 90,
                "minimum_signal_count_recommended": 50,
                "research_only": True,
                "paper_allowed": False,
                "live_allowed": False,
                "real_money_allowed": False,
                "behavior_change_allowed": False,
            }
        ),
        encoding="utf-8",
    )
    (spec_root / "diagnostics" / "shadow_forward_architecture_spec.json").write_text(
        json.dumps(
            {
                "stack": {
                    "execution_engine": "1H",
                    "research_context_timeframe": "6H",
                    "six_h_native_execution": "disabled_weak",
                    "twelve_h_execution": "retired",
                    "aggressive_300k_gear": "shadow_log_only",
                }
            }
        ),
        encoding="utf-8",
    )
    (spec_root / "diagnostics" / "shadow_log_schema.json").write_text(
        json.dumps(
            {
                "ledger/shadow_signal_log.csv": {"required_fields": ["signal_id"]},
                "ledger/shadow_context_log.csv": {"required_fields": ["signal_id"]},
                "ledger/shadow_research_overlay_log.csv": {"required_fields": ["signal_id"]},
                "ledger/shadow_data_quality_log.csv": {"required_fields": ["timestamp"]},
            }
        ),
        encoding="utf-8",
    )
    (spec_root / "diagnostics" / "shadow_readiness_gates.json").write_text(
        json.dumps({"gates": [{"gate": "minimum_shadow_duration"}, {"gate": "minimum_signal_observations"}]}),
        encoding="utf-8",
    )
    (spec_root / "diagnostics" / "replay_vs_forward_consistency_spec.json").write_text(
        json.dumps({"checks": ["signal_reproduction_check", "no_lookahead_check"]}),
        encoding="utf-8",
    )
    broad_root = package_root / "output" / "broad_historical_structural_replay_001" / "ledger"
    broad_root.mkdir(parents=True, exist_ok=True)
    (broad_root / "summary.json").write_text(json.dumps({}), encoding="utf-8")


def _seed_source_csv(root: Path) -> Path:
    source_path = root / "fixture_btcusdt_1m.csv"
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    rows: list[dict[str, object]] = []
    price = 100000.0
    total_minutes = (12 * 24 * 60) + 30
    for index in range(total_minutes):
        ts = start + timedelta(minutes=index)
        drift = 8.0 if (index // 240) % 2 == 0 else -5.0
        wave = ((index % 60) - 30) * 0.6
        open_price = price
        close_price = max(1000.0, price + (drift * 0.04) + (wave * 0.03))
        high_price = max(open_price, close_price) + 6.0
        low_price = min(open_price, close_price) - 6.0
        volume = 120.0 + (index % 25) * 1.4
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


class ShadowForwardObserverTests(unittest.TestCase):
    def test_runtime_defaults_to_dry_run_backfill(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            config = ShadowForwardObserverConfig(
                package_root=package_root,
                output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
            )
            self.assertEqual(DEFAULT_RUNTIME_MODE, config.runtime_mode)

    def test_full_dry_run_backfill_writes_logs_reports_and_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            _seed_shadow_spec(package_root)
            source_csv = _seed_source_csv(Path(tmpdir))

            result = write_shadow_forward_observer(
                ShadowForwardObserverConfig(
                    package_root=package_root,
                    output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
                    source_csv=source_csv,
                    runtime_mode="dry_run_backfill",
                )
            )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("SHADOW_OBSERVER_READY_RESEARCH_ONLY", summary["final_classification"])
            self.assertEqual("dry_run_backfill", summary["runtime_mode_tested"])
            self.assertTrue(summary["prior_shadow_spec_loaded"])
            self.assertTrue(summary["signal_engine_callable_found"])
            self.assertGreater(summary["one_h_decisions_processed"], 0)
            self.assertGreater(summary["six_h_context_annotations_written"], 0)
            self.assertTrue(summary["no_order_path_created"])
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["paper_allowed"])
            self.assertFalse(summary["live_allowed"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertFalse(summary["behavior_change_allowed"])

            output_root = package_root / "output" / OUTPUT_FOLDER_NAME
            diagnostics_root = output_root / "diagnostics"
            ledger_root = output_root / "ledger"
            reports_root = output_root / "reports"

            for path in (
                diagnostics_root / "prior_shadow_spec_anchor.json",
                diagnostics_root / "data_ingestion_status.json",
                diagnostics_root / "replay_vs_forward_consistency_report.json",
                diagnostics_root / "shadow_readiness_progress.json",
                diagnostics_root / "operational_risk_status.json",
                diagnostics_root / "implementation_self_audit.json",
                ledger_root / "shadow_signal_log.csv",
                ledger_root / "shadow_context_log.csv",
                ledger_root / "shadow_research_overlay_log.csv",
                ledger_root / "shadow_data_quality_log.csv",
                reports_root / "daily_shadow_report.md",
                reports_root / "weekly_shadow_report.md",
                reports_root / "monthly_shadow_report.md",
                reports_root / "cumulative_shadow_report.md",
                output_root / "status.json",
                output_root / "scenario_progress.json",
                output_root / "shadow_forward_observer_report.md",
            ):
                self.assertTrue(path.exists(), str(path))

            with (ledger_root / "shadow_signal_log.csv").open(encoding="utf-8") as handle:
                signal_rows = list(csv.DictReader(handle))
            with (ledger_root / "shadow_context_log.csv").open(encoding="utf-8") as handle:
                context_rows = list(csv.DictReader(handle))
            with (ledger_root / "shadow_research_overlay_log.csv").open(encoding="utf-8") as handle:
                overlay_rows = list(csv.DictReader(handle))
            with (ledger_root / "shadow_data_quality_log.csv").open(encoding="utf-8") as handle:
                quality_rows = list(csv.DictReader(handle))

            self.assertEqual(len(signal_rows), len(context_rows))
            self.assertEqual(len(signal_rows), len(overlay_rows))
            self.assertTrue(quality_rows)
            self.assertIn("no_order_sent", signal_rows[0])
            self.assertEqual("True", str(signal_rows[0]["no_order_sent"]))

            last_signal_time = max(pd.Timestamp(row["timestamp"]) for row in signal_rows)
            last_raw_time = pd.Timestamp(datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=(12 * 24 * 60) + 29)).tz_convert(None)
            self.assertLessEqual(last_signal_time, last_raw_time.floor("1h"))

            for row in context_rows:
                if row["context_candle_close_time"]:
                    self.assertLessEqual(pd.Timestamp(row["context_candle_close_time"]), pd.Timestamp(row["timestamp"]))
                self.assertEqual("True", str(row["six_h_execution_disabled"]))
                self.assertEqual("True", str(row["twelve_h_execution_retired"]))

            readiness = json.loads((diagnostics_root / "shadow_readiness_progress.json").read_text(encoding="utf-8"))
            self.assertFalse(readiness["paper_validation_ready"])
            self.assertTrue(readiness["no_order_sent_confirmed"])

            self_audit = json.loads((diagnostics_root / "implementation_self_audit.json").read_text(encoding="utf-8"))
            self.assertTrue(self_audit["no_order_path_created"])
            self.assertTrue(self_audit["no_paper_path_created"])
            self.assertTrue(self_audit["no_live_path_created"])
            self.assertTrue(self_audit["no_broker_execution_created"])
            self.assertFalse(self_audit["previous_artifacts_overwritten"])

    def test_checkpoint_resume_skips_already_processed_closed_candles(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            _seed_shadow_spec(package_root)
            source_csv = _seed_source_csv(Path(tmpdir))

            base_config = dict(
                package_root=package_root,
                output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
                source_csv=source_csv,
                runtime_mode="dry_run_backfill",
            )
            first = write_shadow_forward_observer(ShadowForwardObserverConfig(**base_config, max_decisions=30))
            first_summary = json.loads(first["summary"].read_text(encoding="utf-8"))
            self.assertGreater(first_summary["one_h_decisions_processed"], 0)
            self.assertLess(first_summary["one_h_decisions_processed"], 30)

            second = write_shadow_forward_observer(ShadowForwardObserverConfig(**base_config))
            second_summary = json.loads(second["summary"].read_text(encoding="utf-8"))
            self.assertGreater(second_summary["one_h_decisions_processed"], first_summary["one_h_decisions_processed"])
            checkpoint_index = json.loads((package_root / "output" / OUTPUT_FOLDER_NAME / "_checkpoints" / "checkpoint_index.json").read_text(encoding="utf-8"))
            self.assertTrue(checkpoint_index["last_processed_1h_candle"])


if __name__ == "__main__":
    unittest.main()
