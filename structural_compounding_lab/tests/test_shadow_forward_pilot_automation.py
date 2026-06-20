import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation import (
    OUTPUT_FOLDER_NAME,
    ShadowForwardPilotAutomationConfig,
    run_shadow_forward_pilot_automation,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _seed_safe_shadow_environment(package_root: Path) -> None:
    (package_root / "shadow_forward").mkdir(parents=True, exist_ok=True)
    for name in ("fresh_btcusdt_data_updater.py", "shadow_forward_watchtower.py", "shadow_forward_observer.py"):
        (package_root / "shadow_forward" / name).write_text("# safe research-only stub\n", encoding="utf-8")

    canonical = package_root / "data_storage" / "BTCUSDT" / "1m" / "btcusdt_1m_canonical_shadow_forward.csv"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text("timestamp,open,high,low,close,volume\n2026-06-19T10:59:00,1,2,0.5,1.5,10\n", encoding="utf-8")

    updater_root = package_root / "output" / "fresh_btcusdt_data_updater_001"
    watchtower_root = package_root / "output" / "shadow_forward_watchtower_001"
    _write_json(
        updater_root / "fresh_btcusdt_data_updater_summary.json",
        {
            "resolved_at_utc": "2026-06-19T11:05:00+00:00",
            "final_classification": "FRESH_DATA_READY_AND_WATCHTOWER_STARTED",
            "canonical_path": str(canonical),
            "forward_clock_started": True,
            "latest_canonical_timestamp": "2026-06-19T10:59:00+00:00",
            "rows_fetched": 60,
            "rows_appended": 60,
            "no_order_path_created": True,
            "paper_trade_created": False,
            "live_trade_created": False,
            "broker_execution_created": False,
        },
    )
    _write_json(
        updater_root / "diagnostics" / "implementation_self_audit.json",
        {
            "no_order_path_created": True,
            "no_paper_path_created": True,
            "no_live_path_created": True,
            "broker_execution_created": False,
            "previous_artifacts_overwritten": False,
        },
    )
    _write_json(
        updater_root / "diagnostics" / "fresh_data_quality_audit.json",
        {
            "missing_minute_count_combined_range": 0,
        },
    )
    _write_json(
        watchtower_root / "watchtower_summary.json",
        {
            "final_classification": "WATCHTOWER_READY_BUT_WAITING_FOR_FORWARD_DAYS",
            "no_order_path_created": True,
            "paper_trade_created": False,
            "live_trade_created": False,
            "broker_execution_created": False,
        },
    )
    _write_json(
        watchtower_root / "diagnostics" / "readiness_progress.json",
        {
            "observation_days_completed": 3,
            "observed_1h_decisions": 12,
            "minimum_1h_decisions_required": 50,
            "paper_validation_ready": False,
            "unexplained_missed_signals": 0,
            "data_gap_rate": 0.0,
        },
    )
    _write_json(
        watchtower_root / "diagnostics" / "safety_guard_report.json",
        {
            "passed": True,
        },
    )
    _write_json(
        watchtower_root / "diagnostics" / "future_capital_anchor_plan.json",
        {
            "future_candidate_base_capital_eur": 25000,
            "shadow_mode_uses_capital": False,
            "paper_mode_uses_capital": False,
            "live_mode_uses_capital": False,
            "broker_order_allowed": False,
        },
    )
    _write_json(
        watchtower_root / "diagnostics" / "heartbeat.json",
        {
            "resolved_at_utc": "2026-06-19T11:05:00+00:00",
            "updated_at_utc": "2026-06-19T11:05:00+00:00",
        },
    )
    signal_log = watchtower_root / "ledger" / "watchtower_signal_log.csv"
    signal_log.parent.mkdir(parents=True, exist_ok=True)
    signal_log.write_text(
        "timestamp\n2026-06-19T09:00:00+00:00\n2026-06-19T10:00:00+00:00\n",
        encoding="utf-8",
    )
    run_log = watchtower_root / "ledger" / "watchtower_run_log.csv"
    run_log.write_text(
        "timestamp\n2026-06-19T09:05:00+00:00\n2026-06-19T10:05:00+00:00\n",
        encoding="utf-8",
    )


class ShadowForwardPilotAutomationTests(unittest.TestCase):
    def test_self_check_writes_report_and_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            _seed_safe_shadow_environment(package_root)

            result = run_shadow_forward_pilot_automation(
                ShadowForwardPilotAutomationConfig(
                    package_root=package_root,
                    output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
                    mode="self_check",
                )
            )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self_check = json.loads((package_root / "output" / OUTPUT_FOLDER_NAME / "diagnostics" / "self_check_report.json").read_text(encoding="utf-8"))
            self.assertEqual("AUTOMATION_READY_FOR_MANUAL_APPROVAL", summary["final_classification"])
            self.assertEqual("AUTOMATION_SELF_CHECK_PASSED", self_check["classification"])
            self.assertTrue((package_root / "config" / "shadow_forward_pilot_automation.yaml").exists())

    def test_manual_test_run_can_be_stubbed_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            _seed_safe_shadow_environment(package_root)

            updater_root = package_root / "output" / "fresh_btcusdt_data_updater_001"

            def _fake_updater(config):
                _write_json(
                    updater_root / "fresh_btcusdt_data_updater_summary.json",
                    {
                        "final_classification": "FRESH_DATA_READY_AND_WATCHTOWER_STARTED",
                        "rows_fetched": 12,
                        "rows_appended": 12,
                        "latest_canonical_timestamp": "2026-06-19T11:59:00+00:00",
                    },
                )
                _write_json(
                    updater_root / "diagnostics" / "public_fetch_report.json",
                    {"public_fetch_attempted": True},
                )
                _write_json(
                    updater_root / "diagnostics" / "watchtower_kickoff_report.json",
                    {
                        "newly_processed_1h_decisions": 2,
                        "duplicate_1h_candles_skipped": 0,
                        "heartbeat_updated": True,
                        "readiness_updated": True,
                        "no_order_sent_confirmed": True,
                    },
                )
                return {
                    "summary": updater_root / "fresh_btcusdt_data_updater_summary.json",
                }

            with patch("structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation.write_fresh_btcusdt_data_updater", side_effect=_fake_updater):
                result = run_shadow_forward_pilot_automation(
                    ShadowForwardPilotAutomationConfig(
                        package_root=package_root,
                        output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
                        mode="manual_test_run",
                    )
                )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            manual = json.loads((package_root / "output" / OUTPUT_FOLDER_NAME / "diagnostics" / "manual_test_run_report.json").read_text(encoding="utf-8"))
            self.assertEqual("AUTOMATION_READY_FOR_MANUAL_APPROVAL", summary["final_classification"])
            self.assertTrue(manual["run_success"])
            self.assertTrue(manual["updater_called"])
            self.assertEqual(2, manual["newly_processed_1h_decisions"])

    def test_scheduler_command_generated_but_not_installed_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            _seed_safe_shadow_environment(package_root)
            with patch("structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation._scheduler_task_exists", return_value=False):
                result = run_shadow_forward_pilot_automation(
                    ShadowForwardPilotAutomationConfig(
                        package_root=package_root,
                        output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
                        mode="generate_scheduler_command",
                    )
                )
            report = json.loads((package_root / "output" / OUTPUT_FOLDER_NAME / "diagnostics" / "scheduler_command_report.json").read_text(encoding="utf-8"))
            self.assertEqual("AUTOMATION_READY_FOR_MANUAL_APPROVAL", json.loads(result["summary"].read_text(encoding="utf-8"))["final_classification"])
            self.assertIn("--mode manual_test_run", report["command"])
            self.assertFalse(report["scheduler_installed_by_default"])

    def test_install_and_remove_require_explicit_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            _seed_safe_shadow_environment(package_root)
            run_shadow_forward_pilot_automation(
                ShadowForwardPilotAutomationConfig(
                    package_root=package_root,
                    output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
                    mode="install_scheduler_task",
                )
            )
            install_report = json.loads((package_root / "output" / OUTPUT_FOLDER_NAME / "diagnostics" / "scheduler_install_report.json").read_text(encoding="utf-8"))
            self.assertFalse(install_report["install_attempted"])
            self.assertEqual("explicit_confirmation_required", install_report["blocked_reason"])

            run_shadow_forward_pilot_automation(
                ShadowForwardPilotAutomationConfig(
                    package_root=package_root,
                    output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
                    mode="remove_scheduler_task",
                )
            )
            remove_report = json.loads((package_root / "output" / OUTPUT_FOLDER_NAME / "diagnostics" / "scheduler_remove_report.json").read_text(encoding="utf-8"))
            self.assertFalse(remove_report["remove_attempted"])
            self.assertEqual("explicit_confirmation_required", remove_report["blocked_reason"])

    def test_daily_status_yellow_green_and_red(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            _seed_safe_shadow_environment(package_root)
            frozen_now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)

            with patch("structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation._scheduler_task_exists", return_value=False), patch(
                "structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation._now_utc",
                return_value=frozen_now,
            ):
                run_shadow_forward_pilot_automation(
                    ShadowForwardPilotAutomationConfig(
                        package_root=package_root,
                        output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
                        mode="daily_status",
                    )
                )
            yellow = json.loads((package_root / "output" / OUTPUT_FOLDER_NAME / "diagnostics" / "daily_status.json").read_text(encoding="utf-8"))
            self.assertEqual("YELLOW", yellow["status_color"])

            _write_json(
                package_root / "output" / "shadow_forward_watchtower_001" / "diagnostics" / "heartbeat.json",
                {
                    "resolved_at_utc": "2026-06-19T11:55:00+00:00",
                    "updated_at_utc": "2026-06-19T11:55:00+00:00",
                },
            )
            _write_json(
                package_root / "output" / "fresh_btcusdt_data_updater_001" / "fresh_btcusdt_data_updater_summary.json",
                {
                    "resolved_at_utc": "2026-06-19T11:55:00+00:00",
                    "final_classification": "FRESH_DATA_READY_NO_NEW_ROWS",
                    "canonical_path": str(package_root / "data_storage" / "BTCUSDT" / "1m" / "btcusdt_1m_canonical_shadow_forward.csv"),
                    "forward_clock_started": True,
                    "latest_canonical_timestamp": "2026-06-19T11:55:00+00:00",
                    "rows_fetched": 0,
                    "rows_appended": 0,
                    "no_order_path_created": True,
                    "paper_trade_created": False,
                    "live_trade_created": False,
                    "broker_execution_created": False,
                },
            )
            with patch("structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation._scheduler_task_exists", return_value=True), patch(
                "structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation._now_utc",
                return_value=frozen_now,
            ):
                run_shadow_forward_pilot_automation(
                    ShadowForwardPilotAutomationConfig(
                        package_root=package_root,
                        output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
                        mode="daily_status",
                    )
                )
            green = json.loads((package_root / "output" / OUTPUT_FOLDER_NAME / "diagnostics" / "daily_status.json").read_text(encoding="utf-8"))
            self.assertEqual("GREEN", green["status_color"])

            _write_json(
                package_root / "output" / "shadow_forward_watchtower_001" / "diagnostics" / "future_capital_anchor_plan.json",
                {
                    "future_candidate_base_capital_eur": 25000,
                    "shadow_mode_uses_capital": True,
                    "paper_mode_uses_capital": False,
                    "live_mode_uses_capital": False,
                    "broker_order_allowed": False,
                },
            )
            with patch("structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation._scheduler_task_exists", return_value=True), patch(
                "structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation._now_utc",
                return_value=frozen_now,
            ):
                run_shadow_forward_pilot_automation(
                    ShadowForwardPilotAutomationConfig(
                        package_root=package_root,
                        output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
                        mode="daily_status",
                    )
                )
            red = json.loads((package_root / "output" / OUTPUT_FOLDER_NAME / "diagnostics" / "daily_status.json").read_text(encoding="utf-8"))
            self.assertEqual("RED", red["status_color"])

    def test_docs_scripts_and_final_classification_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "structural_compounding_lab"
            package_root.mkdir(parents=True, exist_ok=True)
            _seed_safe_shadow_environment(package_root)
            with patch("structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation._scheduler_task_exists", return_value=False):
                result = run_shadow_forward_pilot_automation(
                    ShadowForwardPilotAutomationConfig(
                        package_root=package_root,
                        output_root=package_root / "output" / OUTPUT_FOLDER_NAME,
                        mode="status",
                    )
                )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertIn("final_classification", summary)
            self.assertTrue((package_root / "docs" / "shadow_pilot_one_click_guide.md").exists())
            self.assertTrue((package_root.parent / "scripts" / "install_shadow_pilot_task.ps1").exists())
            self.assertTrue((package_root.parent / "scripts" / "remove_shadow_pilot_task.ps1").exists())
            self.assertTrue((package_root.parent / "scripts" / "shadow_pilot_self_check.py").exists())
            self.assertTrue((package_root.parent / "scripts" / "shadow_pilot_run_once.py").exists())
            self.assertTrue((package_root.parent / "scripts" / "shadow_pilot_daily_status.py").exists())


if __name__ == "__main__":
    unittest.main()
