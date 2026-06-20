import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from structural_compounding_lab.shadow_forward.shadow_forward_observer import (
    OUTPUT_FOLDER_NAME as OBSERVER_OUTPUT_FOLDER_NAME,
    ShadowForwardObserverConfig,
    write_shadow_forward_observer,
)
from structural_compounding_lab.shadow_forward.shadow_forward_watchtower import (
    DEFAULT_MODE,
    OUTPUT_FOLDER_NAME,
    ShadowForwardWatchtowerConfig,
    _run_watchtower,
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
            {"band_name": "CONSERVATIVE_TAKER_COST", "total_round_trip_bps": 20.0},
            {"band_name": "HIGH_SLIPPAGE_COST", "total_round_trip_bps": 30.0},
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


def _seed_prior_observer(package_root: Path, source_csv: Path) -> None:
    write_shadow_forward_observer(
        ShadowForwardObserverConfig(
            package_root=package_root,
            output_root=package_root / "output" / OBSERVER_OUTPUT_FOLDER_NAME,
            source_csv=source_csv,
            runtime_mode="dry_run_backfill",
        )
    )


class ShadowForwardWatchtowerTests(unittest.TestCase):
    def test_default_mode_is_single_cycle(self) -> None:
        self.assertEqual("single_cycle", DEFAULT_MODE)

    def test_single_cycle_writes_watchtower_artifacts_and_capital_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            _seed_shadow_spec(package_root)
            source_csv = _seed_source_csv(Path(tmpdir))
            _seed_prior_observer(package_root, source_csv)

            result = _run_watchtower(
                ShadowForwardWatchtowerConfig(
                    package_root=package_root,
                    output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
                    runtime_mode="single_cycle",
                    source_csv=source_csv,
                )
            )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("WATCHTOWER_READY_BUT_WAITING_FOR_FORWARD_DAYS", summary["final_classification"])
            self.assertTrue(summary["safety_guard_passed"])
            self.assertTrue(summary["prior_observer_loaded"])
            self.assertEqual("single_cycle", summary["runtime_mode_tested"])

            output_root = package_root / "output" / OUTPUT_FOLDER_NAME
            heartbeat = json.loads((output_root / "diagnostics" / "heartbeat.json").read_text(encoding="utf-8"))
            readiness = json.loads((output_root / "diagnostics" / "readiness_progress.json").read_text(encoding="utf-8"))
            future_anchor = json.loads((output_root / "diagnostics" / "future_capital_anchor_plan.json").read_text(encoding="utf-8"))
            self_audit = json.loads((output_root / "diagnostics" / "implementation_self_audit.json").read_text(encoding="utf-8"))
            with (output_root / "ledger" / "watchtower_signal_log.csv").open(encoding="utf-8") as handle:
                signal_rows = list(csv.DictReader(handle))

            self.assertGreater(len(signal_rows), 0)
            self.assertEqual(25000, future_anchor["future_candidate_base_capital_eur"])
            self.assertEqual(1062500, future_anchor["projected_5y_equity_reference_eur"])
            self.assertFalse(future_anchor["shadow_mode_uses_capital"])
            self.assertFalse(future_anchor["paper_mode_uses_capital"])
            self.assertFalse(future_anchor["live_mode_uses_capital"])
            self.assertFalse(future_anchor["broker_order_allowed"])
            self.assertTrue(self_audit["future_capital_anchor_recorded"])
            self.assertFalse(self_audit["future_capital_anchor_affects_order_sizing"])
            self.assertFalse(self_audit["future_capital_anchor_affects_shadow_runtime"])
            self.assertTrue(self_audit["capital_activation_blocked_until_future_court"])
            self.assertTrue(heartbeat["no_order_sent_confirmed"])
            self.assertFalse(readiness["paper_validation_ready"])
            self.assertEqual("WATCHTOWER_READY_BUT_WAITING_FOR_FORWARD_DAYS", heartbeat["current_classification"])

            for path in (
                output_root / "status.json",
                output_root / "scenario_progress.json",
                output_root / "watchtower_report.md",
                output_root / "reports" / "cumulative" / "shadow_cumulative_report.md",
                output_root / "reports" / "daily" / f"{readiness['observation_start_date']}_shadow_daily_report.md",
                output_root / "diagnostics" / "safety_guard_report.json",
                output_root / "ledger" / "watchtower_run_log.csv",
                output_root / "_checkpoints" / "watchtower_ingest_checkpoint.json",
            ):
                self.assertTrue(path.exists(), str(path))

    def test_safety_guard_blocks_unsafe_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            _seed_shadow_spec(package_root)
            source_csv = _seed_source_csv(Path(tmpdir))
            _seed_prior_observer(package_root, source_csv)
            config_path = package_root / "config" / "shadow_forward_watchtower.yaml"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                "\n".join(
                    [
                        "research_only: true",
                        "real_money_allowed: false",
                        "paper_allowed: false",
                        "live_allowed: false",
                        "behavior_change_allowed: false",
                        "no_order_path_allowed: true",
                        "append_only_ledgers: true",
                        "allow_private_api_keys: false",
                        "allow_order_endpoints: true",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = _run_watchtower(
                ShadowForwardWatchtowerConfig(
                    package_root=package_root,
                    output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
                    runtime_mode="self_check",
                    config_path=config_path,
                    source_csv=source_csv,
                )
            )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            safety = json.loads((package_root / "output" / OUTPUT_FOLDER_NAME / "diagnostics" / "safety_guard_report.json").read_text(encoding="utf-8"))
            self.assertEqual("WATCHTOWER_BLOCKED_SAFETY_GUARD_FAILED", summary["final_classification"])
            self.assertFalse(safety["passed"])

    def test_append_only_resume_does_not_duplicate_candles(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            _seed_shadow_spec(package_root)
            source_csv = _seed_source_csv(Path(tmpdir))
            _seed_prior_observer(package_root, source_csv)
            output_root = package_root / "output" / OUTPUT_FOLDER_NAME

            config = ShadowForwardWatchtowerConfig(
                package_root=package_root,
                output_root=output_root,
                runtime_mode="single_cycle",
                source_csv=source_csv,
            )
            _run_watchtower(config)
            with (output_root / "ledger" / "watchtower_signal_log.csv").open(encoding="utf-8") as handle:
                first_rows = list(csv.DictReader(handle))
            _run_watchtower(config)
            with (output_root / "ledger" / "watchtower_signal_log.csv").open(encoding="utf-8") as handle:
                second_rows = list(csv.DictReader(handle))
            self.assertEqual(len(first_rows), len(second_rows))

    def test_missing_prior_observer_blocks_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            _seed_shadow_spec(package_root)
            output_root = package_root / "output" / OUTPUT_FOLDER_NAME
            result = _run_watchtower(
                ShadowForwardWatchtowerConfig(
                    package_root=package_root,
                    output_root=output_root,
                    runtime_mode="status",
                )
            )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("WATCHTOWER_BLOCKED_OBSERVER_NOT_READY", summary["final_classification"])

    def test_repo_docs_and_helper_scripts_exist(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.assertTrue((repo_root / "scripts" / "run_shadow_watchtower_once.py").exists())
        self.assertTrue((repo_root / "scripts" / "run_shadow_watchtower_once.bat").exists())
        self.assertTrue((repo_root / "structural_compounding_lab" / "docs" / "shadow_forward_watchtower_runbook.md").exists())
        self.assertTrue((repo_root / "structural_compounding_lab" / "docs" / "windows_task_scheduler_shadow_watchtower.md").exists())


if __name__ == "__main__":
    unittest.main()
