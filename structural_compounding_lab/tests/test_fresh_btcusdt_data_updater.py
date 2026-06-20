import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater import (
    OUTPUT_FOLDER_NAME,
    FreshBTCUSDTDataUpdaterConfig,
    write_fresh_btcusdt_data_updater,
)
from structural_compounding_lab.shadow_forward.shadow_forward_observer import (
    OUTPUT_FOLDER_NAME as OBSERVER_OUTPUT_FOLDER_NAME,
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


def _seed_source_csv(root: Path, *, source_end: datetime, hours_history: int = 72) -> Path:
    storage_path = root / "data_storage" / "BTCUSDT" / "1m" / "BTCUSDT_1m_2018-01-01_to_2026-06-13.csv"
    start = source_end - timedelta(hours=hours_history) + timedelta(minutes=1)
    rows: list[dict[str, object]] = []
    price = 100000.0
    total_minutes = int(((source_end - start).total_seconds() // 60) + 1)
    for index in range(total_minutes):
        ts = start + timedelta(minutes=index)
        drift = 5.0 if (index // 120) % 2 == 0 else -2.5
        open_price = price
        close_price = max(1000.0, price + drift * 0.05 + ((index % 30) - 15) * 0.02)
        rows.append(
            {
                "timestamp": ts.isoformat(),
                "open": round(open_price, 6),
                "high": round(max(open_price, close_price) + 4.0, 6),
                "low": round(min(open_price, close_price) - 4.0, 6),
                "close": round(close_price, 6),
                "volume": round(100 + (index % 20), 6),
            }
        )
        price = close_price
    _write_csv(storage_path, rows)
    return storage_path


def _seed_prior_observer(package_root: Path, source_csv: Path) -> None:
    write_shadow_forward_observer(
        ShadowForwardObserverConfig(
            package_root=package_root,
            output_root=package_root / "output" / OBSERVER_OUTPUT_FOLDER_NAME,
            source_csv=source_csv,
            runtime_mode="dry_run_backfill",
        )
    )


def _fake_kline_rows(start: datetime, minutes: int) -> list[list[object]]:
    rows: list[list[object]] = []
    price = 101000.0
    for index in range(minutes):
        ts = start + timedelta(minutes=index)
        open_price = price
        close_price = price + 1.0
        open_ms = int(ts.timestamp() * 1000)
        close_ms = int((ts + timedelta(minutes=1) - timedelta(milliseconds=1)).timestamp() * 1000)
        rows.append(
            [
                open_ms,
                f"{open_price:.6f}",
                f"{(close_price + 2.0):.6f}",
                f"{(open_price - 2.0):.6f}",
                f"{close_price:.6f}",
                "120.0",
                close_ms,
                "1000.0",
                10,
                "55.0",
                "500.0",
                "0",
            ]
        )
        price = close_price
    return rows


class _MockResponse:
    def __init__(self, payload: list[list[object]], status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http_{self.status_code}")


class FreshBTCUSDTDataUpdaterTests(unittest.TestCase):
    def test_source_discovery_and_fetch_window_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            _seed_shadow_spec(package_root)
            source_end = datetime(2026, 6, 13, 0, 0, tzinfo=timezone.utc)
            source_csv = _seed_source_csv(Path(tmpdir), source_end=source_end)
            _seed_prior_observer(package_root, source_csv)

            result = write_fresh_btcusdt_data_updater(
                FreshBTCUSDTDataUpdaterConfig(
                    package_root=package_root,
                    output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
                    mode="update_only",
                    dry_run=True,
                    max_fetch_minutes=120,
                )
            )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            source_report = json.loads((package_root / "output" / OUTPUT_FOLDER_NAME / "diagnostics" / "source_discovery_report.json").read_text(encoding="utf-8"))
            fetch_window = json.loads((package_root / "output" / OUTPUT_FOLDER_NAME / "diagnostics" / "fetch_window_plan.json").read_text(encoding="utf-8"))
            self.assertTrue(source_report["source_is_valid"])
            self.assertIn("BTCUSDT_1m_2018-01-01_to_2026-06-13.csv", source_report["selected_source_path"])
            self.assertEqual("FRESH_DATA_READY_NO_NEW_ROWS", summary["final_classification"])
            self.assertEqual("2026-06-13T00:01:00", fetch_window["fetch_start_timestamp"])
            self.assertTrue(fetch_window["incomplete_current_hour_excluded"])

    def test_public_fetch_normalization_and_canonical_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            _seed_shadow_spec(package_root)
            source_end = datetime(2026, 6, 13, 0, 0, tzinfo=timezone.utc)
            source_csv = _seed_source_csv(Path(tmpdir), source_end=source_end)
            _seed_prior_observer(package_root, source_csv)
            fetched_rows = _fake_kline_rows(source_end + timedelta(minutes=1), 120)

            with patch("structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater.requests.get", return_value=_MockResponse(fetched_rows)):
                result = write_fresh_btcusdt_data_updater(
                    FreshBTCUSDTDataUpdaterConfig(
                        package_root=package_root,
                        output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
                        mode="update_only",
                        max_fetch_minutes=120,
                    )
                )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            fetch_report = json.loads((package_root / "output" / OUTPUT_FOLDER_NAME / "diagnostics" / "public_fetch_report.json").read_text(encoding="utf-8"))
            canonical_report = json.loads((package_root / "output" / OUTPUT_FOLDER_NAME / "diagnostics" / "canonical_write_report.json").read_text(encoding="utf-8"))
            self.assertEqual("FRESH_DATA_READY_AND_APPENDED", summary["final_classification"])
            self.assertFalse(fetch_report["private_api_key_used"])
            self.assertFalse(fetch_report["account_endpoint_used"])
            self.assertFalse(fetch_report["order_endpoint_used"])
            self.assertEqual(120, fetch_report["fetched_rows"])
            self.assertTrue(Path(canonical_report["canonical_path"]).exists())
            self.assertEqual(120, canonical_report["new_rows_appended"])

    def test_update_and_catchup_starts_forward_clock_only_after_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            _seed_shadow_spec(package_root)
            source_end = datetime(2026, 6, 13, 0, 0, tzinfo=timezone.utc)
            source_csv = _seed_source_csv(Path(tmpdir), source_end=source_end)
            _seed_prior_observer(package_root, source_csv)
            fetched_rows = _fake_kline_rows(source_end + timedelta(minutes=1), 240)

            with patch("structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater.requests.get", return_value=_MockResponse(fetched_rows)):
                result = write_fresh_btcusdt_data_updater(
                    FreshBTCUSDTDataUpdaterConfig(
                        package_root=package_root,
                        output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
                        mode="update_and_catchup",
                        max_fetch_minutes=240,
                    )
                )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            kickoff = json.loads((package_root / "output" / OUTPUT_FOLDER_NAME / "diagnostics" / "watchtower_kickoff_report.json").read_text(encoding="utf-8"))
            readiness = json.loads((package_root / "output" / "shadow_forward_watchtower_001" / "diagnostics" / "readiness_progress.json").read_text(encoding="utf-8"))
            self.assertEqual("FRESH_DATA_READY_AND_WATCHTOWER_STARTED", summary["final_classification"])
            self.assertTrue(kickoff["watchtower_run_attempted"])
            self.assertTrue(kickoff["forward_clock_started"])
            self.assertGreater(kickoff["newly_processed_1h_decisions"], 0)
            self.assertEqual(1, readiness["observation_days_completed"])
            self.assertGreater(readiness["observed_1h_decisions"], 0)

    def test_safety_guard_blocks_fake_unsafe_canonical_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            _seed_shadow_spec(package_root)
            source_end = datetime(2026, 6, 13, 0, 0, tzinfo=timezone.utc)
            source_csv = _seed_source_csv(Path(tmpdir), source_end=source_end)
            _seed_prior_observer(package_root, source_csv)

            result = write_fresh_btcusdt_data_updater(
                FreshBTCUSDTDataUpdaterConfig(
                    package_root=package_root,
                    output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
                    mode="update_only",
                    dry_run=True,
                    canonical_path=package_root / "data_storage" / "BTCUSDT" / "1m" / "order_shadow.csv",
                )
            )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("FRESH_DATA_BLOCKED_SAFETY_GUARD_FAILED", summary["final_classification"])

    def test_resume_dedupes_existing_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            _seed_shadow_spec(package_root)
            source_end = datetime(2026, 6, 13, 0, 0, tzinfo=timezone.utc)
            source_csv = _seed_source_csv(Path(tmpdir), source_end=source_end)
            _seed_prior_observer(package_root, source_csv)
            fetched_rows = _fake_kline_rows(source_end + timedelta(minutes=1), 60)
            updater_config = FreshBTCUSDTDataUpdaterConfig(
                package_root=package_root,
                output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
                mode="update_only",
                max_fetch_minutes=60,
            )

            with patch("structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater.requests.get", return_value=_MockResponse(fetched_rows)):
                write_fresh_btcusdt_data_updater(updater_config)
            with patch("structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater.requests.get", return_value=_MockResponse(fetched_rows)):
                result = write_fresh_btcusdt_data_updater(updater_config)

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("FRESH_DATA_READY_NO_NEW_ROWS", summary["final_classification"])
            self.assertEqual(0, summary["rows_appended"])

    def test_rerun_preserves_original_forward_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            _seed_shadow_spec(package_root)
            source_end = datetime(2026, 6, 13, 0, 0, tzinfo=timezone.utc)
            source_csv = _seed_source_csv(Path(tmpdir), source_end=source_end)
            _seed_prior_observer(package_root, source_csv)
            fetched_rows = _fake_kline_rows(source_end + timedelta(minutes=1), 180)
            updater_config = FreshBTCUSDTDataUpdaterConfig(
                package_root=package_root,
                output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
                mode="update_and_catchup",
                max_fetch_minutes=180,
            )

            with patch("structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater.requests.get", return_value=_MockResponse(fetched_rows)):
                write_fresh_btcusdt_data_updater(updater_config)
            with patch("structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater.requests.get", return_value=_MockResponse([])):
                write_fresh_btcusdt_data_updater(updater_config)

            policy = json.loads(
                (package_root / "output" / "shadow_forward_watchtower_001" / "diagnostics" / "forward_clock_policy.json").read_text(encoding="utf-8")
            )
            self.assertEqual("2026-06-13T00:00:00", policy["stale_historical_boundary_timestamp"])
            self.assertTrue(policy["preserved_existing_boundary"])


if __name__ == "__main__":
    unittest.main()
