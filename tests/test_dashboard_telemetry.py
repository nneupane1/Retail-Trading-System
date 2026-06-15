import json
import tempfile
import unittest
from pathlib import Path

from common.dashboard_telemetry import build_trade_markers, list_live_runs, load_live_dashboard_snapshot, load_symbol_candles


class DummyConfig:
    def __init__(self, root_dir):
        self.root_dir = Path(root_dir)
        self.config_path = self.root_dir / "config" / "settings.json"
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            self.config_path.write_text("{}", encoding="utf-8")
        self.data = {
            "live_sim": {
                "output_dir": str(self.root_dir / "live_output"),
            },
            "backtest": {
                "output_dir": str(self.root_dir / "backtest" / "output"),
            },
            "storage": {
                "base_path": str(self.root_dir / "data_storage"),
            },
            "binance": {
                "default_interval": "1m",
                "ssl_verify": True,
                "ca_bundle_path": None,
            },
            "history": {
                "start_date": "2018-01-01",
                "end_date": "2026-05-12",
            },
            "account": {"initial_equity": 20000, "risk_per_trade": 0.01},
            "strategy": {
                "moonshots": {"swing": {"enabled": True}},
                "h1_execution": {"enabled": True},
                "htf_12h_standard": {"enabled": True},
                "htf_12h_moonshot": {"enabled": True},
                "htf_12h_rotation": {"enabled": True},
                "h6_standard": {"enabled": False},
                "h6_moonshot": {"enabled": False},
                "daily_controls": {"enabled": True},
            },
            "universe": {
                "symbol_sets": {
                    "current_9": [
                        "AAVEUSDT",
                        "AVAXUSDT",
                        "BNBUSDT",
                        "BTCUSDT",
                        "ETHUSDT",
                        "LINKUSDT",
                        "SOLUSDT",
                        "TRXUSDT",
                        "XRPUSDT",
                    ]
                }
            },
        }
        self.data["live_sim"]["mode"] = "portfolio_paper"
        self.data["live_sim"]["paper_portfolio"] = {
            "allowed_sides": ["long"],
            "allowed_edge_types": ["impulse_breakout"],
            "allocator_v2": {"enabled": True},
            "strategy_allowed_sides": {
                "h1_execution": ["short"],
                "htf_12h_standard": ["long"],
                "htf_12h_moonshot": ["long"],
                "htf_12h_rotation": ["long"],
                "h6_standard": ["long"],
            },
        }

    def require(self, *keys):
        value = self.data
        for key in keys:
            value = value[key]
        return value

    def get(self, *keys, default=None):
        value = self.data
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value

    def path(self, *keys, default=None):
        value = self.get(*keys, default=default)
        if value is None:
            return None
        return Path(value)


def _write_gate_artifacts(root: Path) -> None:
    gate_root = root / "backtest" / "output" / "production_validation_gate_current"
    gate_root.mkdir(parents=True, exist_ok=True)
    status = {
        "stage": "complete",
        "summary_path": str(gate_root / "summary.json"),
        "promotion_readiness_report_path": str(gate_root / "promotion_readiness_report.json"),
        "real_money_ready": False,
        "blockers": ["binance_ssl_verify_enabled"],
    }
    summary = {
        "latest_common_data_timestamp": "2026-06-13T00:00:00+00:00",
        "scenarios": {
            "full_history_latest_closed_day": {
                "name": "scenario_current_routed_stack_full_history_latest_closed_day",
                "output_dir": str(gate_root / "scenario_current_routed_stack_full_history_latest_closed_day"),
                "metrics": {"profit_factor": 1.26, "net_pnl": 36365.2},
            },
            "trailing_12m_holdout": {
                "name": "scenario_current_routed_stack_trailing_12m_holdout",
                "output_dir": str(gate_root / "scenario_current_routed_stack_trailing_12m_holdout"),
                "metrics": {"profit_factor": 1.02, "net_pnl": 188.53},
            },
        },
    }
    report = {
        "real_money_ready": False,
        "blockers": ["binance_ssl_verify_enabled"],
        "checks": [
            {"name": "full_history_artifacts_complete", "status": "pass", "passed": True},
            {"name": "full_history_positive_expectancy", "status": "pass", "passed": True},
            {"name": "holdout_artifacts_complete", "status": "pass", "passed": True},
            {"name": "holdout_positive_expectancy", "status": "pass", "passed": True},
            {"name": "restart_restore_guarantees_present", "status": "pass", "passed": True},
        ],
    }
    (gate_root / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (gate_root / "promotion_readiness_report.json").write_text(json.dumps(report), encoding="utf-8")
    (gate_root / "status.json").write_text(json.dumps(status), encoding="utf-8")


class DashboardTelemetryTests(unittest.TestCase):
    def test_load_live_dashboard_snapshot_reads_status_and_csvs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config = DummyConfig(tmpdir)
            _write_gate_artifacts(root)
            (root / "portfolio_status.json").write_text(
                json.dumps({"equity": 12345, "runtime_policy_states": {"h1_execution": {"label": "boost_active"}}}),
                encoding="utf-8",
            )
            (root / "paper_soak_status.json").write_text(
                json.dumps(
                    {
                        "classification": "paper-only",
                        "paper_runtime_allowed": True,
                        "real_money_allowed": False,
                        "ssl_verify": True,
                        "validated_boundary": "2026-06-13T00:00:00+00:00",
                        "runtime_started_at": "2026-06-14T00:00:00+00:00",
                        "runtime_last_processed_timestamp": "2026-06-14T00:14:00+00:00",
                        "open_positions_count": 1,
                        "warning_list": [],
                    }
                ),
                encoding="utf-8",
            )
            (root / "paper_soak_daily_report.json").write_text(
                json.dumps(
                    {
                        "report_generated_at_utc": "2026-06-14T00:30:00+00:00",
                        "classification": "paper-only",
                        "paper_runtime_allowed": True,
                        "real_money_allowed": False,
                        "current_paper_equity": 12345,
                        "daily_pnl": 50.0,
                        "open_positions": 1,
                        "active_sleeves": ["core", "h1_execution"],
                        "disabled_sleeves": ["h6_standard", "h6_moonshot"],
                        "warning_list": [],
                        "promotion_criteria": {
                            "promotion_status": "paper_soak_in_progress"
                        },
                    }
                ),
                encoding="utf-8",
            )
            (root / "paper_soak_review.json").write_text(
                json.dumps(
                    {
                        "review_generated_at_utc": "2026-06-14T00:35:00+00:00",
                        "classification": "paper-only",
                        "paper_runtime_allowed": True,
                        "real_money_allowed": False,
                        "soak_days_completed": 0.5,
                        "required_soak_days": 14,
                        "soak_review_status": "insufficient_forward_paper_duration",
                        "heartbeat_health": "healthy",
                        "restart_count": 1,
                        "successful_restore_count": 1,
                        "h1_short_override_status": True,
                        "h6_disabled_status": True,
                        "warning_list": [],
                        "soak_review_criteria": {
                            "h6_routes_zero_trades": {"status": "pass"},
                            "h1_short_override_active": {"status": "pass"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            (root / "paper_soak_review_history.jsonl").write_text(
                json.dumps(
                    {
                        "timestamp": "2026-06-14T00:35:00+00:00",
                        "soak_days_completed": 0.5,
                        "current_equity": 12345,
                        "realized_pnl": 45.0,
                        "drawdown_fraction": 0.01,
                        "blockers": [],
                        "warnings": [],
                        "soak_review_status": "insufficient_forward_paper_duration",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "baseline_freeze_snapshot.json").write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-06-14T00:40:00+00:00",
                        "classification": "paper-only",
                        "paper_runtime_allowed": True,
                        "real_money_allowed": False,
                        "ssl_verify": True,
                        "minimum_soak_days": 14,
                        "current_soak_days": 0.5,
                        "manual_review_status": "governance_only",
                        "manual_review": {
                            "manual_review_outcome": "continue_paper_soak",
                            "automatic_real_money_promotion": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            (root / "capital_refactor").mkdir(parents=True, exist_ok=True)
            (root / "capital_refactor" / "scaffold_inventory.json").write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-06-14T00:45:00+00:00",
                        "classification": "paper-only",
                        "paper_runtime_allowed": True,
                        "real_money_allowed": False,
                        "validated_boundary": "2026-06-13T00:00:00+00:00",
                        "ssl_verify": True,
                        "capital_refactor_enabled": False,
                        "behavior_change_allowed": False,
                        "modules_present": {
                            "capital_lanes": True,
                            "risk_bands": True,
                        },
                        "layer_statuses": {
                            "capital_lanes": {
                                "present": True,
                                "enabled": False,
                                "behavior_change_allowed": False,
                            }
                        },
                        "promotion_review": {
                            "status": "scaffold_only",
                            "behavior_change_allowed": False,
                            "real_money_allowed": False,
                        },
                        "warning": "scaffold_only_no_trading_behavior_change",
                    }
                ),
                encoding="utf-8",
            )
            diagnostics_root = root / "backtest" / "output" / "capital_refactor" / "diagnostics"
            diagnostics_root.mkdir(parents=True, exist_ok=True)
            (diagnostics_root / "diagnostics_summary.json").write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-06-14T00:50:00+00:00",
                        "phase": "phase_1_diagnostics_only",
                        "classification": "paper-only",
                        "paper_runtime_allowed": True,
                        "real_money_allowed": False,
                        "behavior_change_allowed": False,
                        "diagnostics_only": True,
                        "allocator_behavior_changed": False,
                        "risk_behavior_changed": False,
                        "sizing_behavior_changed": False,
                        "entry_behavior_changed": False,
                        "exit_behavior_changed": False,
                        "warnings": ["diagnostics_only_no_trading_behavior_change"],
                    }
                ),
                encoding="utf-8",
            )
            for name in (
                "rejection_shadow_book.csv",
                "capital_blocked_winners.csv",
                "top_winner_forensics.csv",
            ):
                (diagnostics_root / name).write_text("timestamp,symbol\n", encoding="utf-8")
            (diagnostics_root / "strategy_bucket_capital_efficiency.json").write_text(
                json.dumps({"generated_at_utc": "2026-06-14T00:50:00+00:00", "groups": []}),
                encoding="utf-8",
            )
            (diagnostics_root / "opportunity_cost_report.json").write_text(
                json.dumps({"generated_at_utc": "2026-06-14T00:50:00+00:00", "observations": []}),
                encoding="utf-8",
            )
            review_root = diagnostics_root / "review"
            review_root.mkdir(parents=True, exist_ok=True)
            (review_root / "phase1_evidence_review.json").write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-06-14T00:55:00+00:00",
                        "phase": "phase_1_evidence_review",
                        "evidence_strength": {
                            "overall": "moderate_backtest_only",
                            "phase2_backtest_only_justified": True,
                            "recommended_next_phase": "phase_2_backtest_only_capital_lane_experiment",
                        },
                        "behavior_change_allowed": False,
                        "real_money_allowed": False,
                        "allocator_behavior_changed": False,
                        "risk_behavior_changed": False,
                        "sizing_behavior_changed": False,
                        "entry_behavior_changed": False,
                        "exit_behavior_changed": False,
                        "thresholds_changed": False,
                        "sleeves_changed": False,
                        "six_h_enabled": False,
                        "h1_short_override_active": True,
                        "top_rejection_reasons": [
                            {"rejection_reason": "shared_risk_cap", "count": 12},
                        ],
                        "top_blocking_constraints": [
                            {"blocking_constraint": "shared_risk_cap", "count": 6},
                        ],
                        "phase2_not_allowed_yet_reasoning": [
                            "review gate only",
                        ],
                        "warnings": ["diagnostics_only_no_trading_behavior_change"],
                    }
                ),
                encoding="utf-8",
            )
            (review_root / "phase1_evidence_review.md").write_text(
                "# review\n",
                encoding="utf-8",
            )
            (review_root / "phase2_experiment_brief.md").write_text(
                "# brief\n",
                encoding="utf-8",
            )
            (review_root / "status.json").write_text(
                json.dumps({"phase": "phase_1_evidence_review", "stage": "complete"}),
                encoding="utf-8",
            )
            (root / "paper_runtime_events.jsonl").write_text(
                json.dumps(
                    {
                        "startup_time": "2026-06-14T00:00:00+00:00",
                        "restore_happened": True,
                        "restored_positions_count": 1,
                        "validation_boundary": "2026-06-13T00:00:00+00:00",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "portfolio_runtime_state.json").write_text(
                json.dumps({"open_positions": []}),
                encoding="utf-8",
            )
            (root / "runtime_policy_summary.csv").write_text(
                "strategy_type,enabled,label,fallback_to_short_only,count,avg_R,profit_factor,min_trades,min_avg_R,min_profit_factor\n"
                "h1_execution,True,boost_active,False,80,0.1,1.3,24,0.02,1.05\n",
                encoding="utf-8",
            )
            (root / "selection_reason_summary.csv").write_text(
                "selection_reason,count,share_of_decisions,is_cap_pressure\nopened,12,0.5,False\n",
                encoding="utf-8",
            )
            (root / "recent_selection_reason_summary.csv").write_text(
                "selection_reason,count,share_of_decisions,is_cap_pressure\nshared_risk_cap,2,0.2,True\n",
                encoding="utf-8",
            )
            (root / "selection_reason_by_strategy_summary.csv").write_text(
                "strategy_type,selection_reason,count,share_of_strategy_decisions,is_cap_pressure\ncore,opened,10,0.5,False\n",
                encoding="utf-8",
            )
            (root / "allocator_decisions.csv").write_text(
                "timestamp,candidate_id,symbol,side,strategy_type,final_reason,opened,selection_score,threshold\n"
                "2026-06-06 00:15:00,0,BTCUSDT,long,core,opened,True,0.91,0.82\n",
                encoding="utf-8",
            )
            (root / "daily_summary.csv").write_text(
                "date,equity_start,equity_end,realized_pnl,realized_return_fraction,entries_taken,closed_trades,threshold\n"
                "2026-06-06,10000,10100,100,0.01,3,2,0.82\n",
                encoding="utf-8",
            )
            (root / "trades.csv").write_text(
                "trade_id,symbol,side,entry_time,exit_time,pnl,strategy_type\n"
                "t1,BTCUSDT,long,2026-06-06 00:00:00,2026-06-06 01:00:00,12.5,core\n",
                encoding="utf-8",
            )
            (root / "signals.csv").write_text(
                "timestamp,symbol,side,selection_reason,strategy_type\n"
                "2026-06-06 00:00:00,BTCUSDT,long,opened,core\n",
                encoding="utf-8",
            )
            (root / "engine_heartbeat.json").write_text(
                json.dumps(
                    {
                        "cycle_count": 7,
                        "status": "routed_candidates",
                        "latest_recent_1m_timestamp": "2026-06-06 00:14:00",
                        "candidates_built": 3,
                    }
                ),
                encoding="utf-8",
            )
            (root / "engine_cycle_history.csv").write_text(
                "cycle_count,status,cycle_started_at,cycle_completed_at,cycle_duration_seconds,poll_seconds,symbol_count,symbols_with_recent_fetch,total_recent_1m_rows,total_state_1m_rows,latest_recent_1m_timestamp,new_15m_symbol_count,new_15m_symbols,candidates_built,eligible_candidates,allocated_candidates,opened_count,top_symbols,portfolio_open_positions,equity\n"
                "7,routed_candidates,2026-06-06T00:14:00Z,2026-06-06T00:14:02Z,2.0,30.0,2,2,800,20000,2026-06-06 00:14:00,1,BTCUSDT,3,2,2,1,BTCUSDT|ETHUSDT,1,12345\n",
                encoding="utf-8",
            )
            (root / "symbol_pipeline_status.csv").write_text(
                "symbol,recent_rows_1m,state_rows_1m,latest_recent_1m_timestamp,latest_15m_timestamp,latest_1h_timestamp,latest_6h_timestamp,latest_12h_timestamp,latest_1d_timestamp,new_15m_candle,candidate_count,candidate_strategies,top_mover,momentum_rank\n"
                "BTCUSDT,400,10000,2026-06-06 00:14:00,2026-06-06 00:00:00,2026-06-06 00:00:00,2026-06-06 00:00:00,2026-06-06 00:00:00,2026-06-06 00:00:00,True,2,core|h1_execution,True,0.99\n",
                encoding="utf-8",
            )

            soak_before = (root / "paper_soak_status.json").read_text(encoding="utf-8")
            payload = load_live_dashboard_snapshot(root, config=config)

            self.assertEqual(12345, payload["portfolio_status"]["equity"])
            self.assertEqual("boost_active", payload["runtime_policy_rows"][0]["label"])
            self.assertEqual("opened", payload["selection_reason_rows"][0]["selection_reason"])
            self.assertEqual("shared_risk_cap", payload["recent_selection_reason_rows"][0]["selection_reason"])
            self.assertEqual("BTCUSDT", payload["trade_rows"][0]["symbol"])
            self.assertEqual("core", payload["signal_rows"][0]["strategy_type"])
            self.assertEqual(["BTCUSDT"], payload["available_symbols"])
            self.assertEqual(7, payload["engine_heartbeat"]["cycle_count"])
            self.assertEqual("routed_candidates", payload["engine_cycle_rows"][0]["status"])
            self.assertEqual("BTCUSDT", payload["symbol_pipeline_rows"][0]["symbol"])
            self.assertEqual("opened", payload["allocator_decision_rows"][0]["final_reason"])
            self.assertEqual("paper-only", payload["paper_soak_status"]["classification"])
            self.assertTrue(payload["paper_soak_status"]["paper_runtime_allowed"])
            self.assertFalse(payload["paper_soak_status"]["real_money_allowed"])
            self.assertEqual("paper_soak_in_progress", payload["paper_soak_daily_report"]["promotion_criteria"]["promotion_status"])
            self.assertFalse(payload["paper_soak_daily_report"]["real_money_allowed"])
            self.assertEqual("insufficient_forward_paper_duration", payload["paper_soak_review"]["soak_review_status"])
            self.assertFalse(payload["paper_soak_review"]["real_money_allowed"])
            self.assertEqual("continue_paper_soak", payload["baseline_freeze_snapshot"]["manual_review"]["manual_review_outcome"])
            self.assertFalse(payload["baseline_freeze_snapshot"]["real_money_allowed"])
            self.assertFalse(payload["capital_refactor_scaffold_inventory"]["capital_refactor_enabled"])
            self.assertFalse(payload["capital_refactor_scaffold_inventory"]["behavior_change_allowed"])
            self.assertEqual("scaffold_only", payload["capital_refactor_scaffold_inventory"]["promotion_review"]["status"])
            self.assertEqual("phase_1_diagnostics_only", payload["capital_refactor_phase1_diagnostics"]["phase"])
            self.assertFalse(payload["capital_refactor_phase1_diagnostics"]["real_money_allowed"])
            self.assertEqual("phase_1_evidence_review", payload["capital_refactor_phase1_evidence_review"]["phase"])
            self.assertTrue(payload["capital_refactor_phase1_evidence_review"]["evidence_strength"]["phase2_backtest_only_justified"])
            self.assertEqual("complete", payload["validation_truth"]["validation_status"])
            self.assertEqual("pass", payload["validation_truth"]["full_history_verdict"])
            self.assertEqual("pass", payload["validation_truth"]["trailing_holdout_verdict"])
            self.assertIn("baseline_freeze_snapshot", payload["artifact_freshness"])
            self.assertEqual("healthy", payload["artifact_freshness"]["baseline_freeze_snapshot"]["status"])
            self.assertIn("capital_refactor_phase1_diagnostics_summary", payload["artifact_freshness"])
            self.assertEqual("healthy", payload["artifact_freshness"]["capital_refactor_phase1_diagnostics_summary"]["status"])
            self.assertIn("capital_refactor_phase1_evidence_review_json", payload["artifact_freshness"])
            self.assertEqual("healthy", payload["artifact_freshness"]["capital_refactor_phase1_evidence_review_json"]["status"])
            self.assertIn("paper_soak_daily_report", payload["artifact_freshness"])
            self.assertEqual("healthy", payload["artifact_freshness"]["paper_soak_daily_report"]["status"])
            self.assertIn("paper_soak_review", payload["artifact_freshness"])
            self.assertEqual("healthy", payload["artifact_freshness"]["paper_soak_review"]["status"])
            self.assertIn("paper_soak_review_history", payload["artifact_freshness"])
            self.assertEqual("healthy", payload["artifact_freshness"]["paper_soak_review_history"]["status"])
            self.assertIn("paper_soak_status", payload["artifact_freshness"])
            self.assertEqual("healthy", payload["artifact_freshness"]["paper_soak_status"]["status"])
            self.assertIn("capital_refactor_scaffold_inventory", payload["artifact_freshness"])
            self.assertEqual("healthy", payload["artifact_freshness"]["capital_refactor_scaffold_inventory"]["status"])
            self.assertEqual("healthy", payload["artifact_freshness"]["portfolio_status"]["status"])
            self.assertEqual("2026-06-14T00:00:00+00:00", payload["last_runtime_event"]["startup_time"])
            self.assertFalse(payload["readiness"]["real_money_allowed"])
            self.assertIn("h6_standard", payload["readiness"]["runtime_config"]["disabled_sleeves"])
            self.assertEqual(
                ["short"],
                payload["readiness"]["runtime_config"]["strategy_allowed_sides"]["h1_execution"],
            )
            self.assertEqual(soak_before, (root / "paper_soak_status.json").read_text(encoding="utf-8"))

    def test_load_live_dashboard_snapshot_reports_missing_artifacts_gracefully(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config = DummyConfig(tmpdir)
            _write_gate_artifacts(root)
            (root / "portfolio_status.json").write_text(json.dumps({"equity": 20000}), encoding="utf-8")

            payload = load_live_dashboard_snapshot(root, config=config)

            self.assertEqual("missing", payload["artifact_freshness"]["baseline_freeze_snapshot"]["status"])
            self.assertEqual("missing", payload["artifact_freshness"]["capital_refactor_phase1_diagnostics_summary"]["status"])
            self.assertEqual("missing", payload["artifact_freshness"]["capital_refactor_phase1_evidence_review_json"]["status"])
            self.assertEqual("missing", payload["artifact_freshness"]["paper_soak_daily_report"]["status"])
            self.assertEqual("missing", payload["artifact_freshness"]["paper_soak_review"]["status"])
            self.assertEqual("missing", payload["artifact_freshness"]["paper_soak_review_history"]["status"])
            self.assertIn("missing_artifact:capital_refactor_phase1_diagnostics_summary", payload["operator_warning_list"])
            self.assertIn("missing_artifact:capital_refactor_phase1_evidence_review_json", payload["operator_warning_list"])
            self.assertIn("missing_artifact:baseline_freeze_snapshot", payload["operator_warning_list"])
            self.assertEqual("missing", payload["artifact_freshness"]["capital_refactor_scaffold_inventory"]["status"])
            self.assertEqual("missing", payload["artifact_freshness"]["paper_soak_status"]["status"])
            self.assertEqual("missing", payload["artifact_freshness"]["paper_runtime_events"]["status"])
            self.assertIn("missing_artifact:capital_refactor_scaffold_inventory", payload["operator_warning_list"])
            self.assertIn("missing_artifact:paper_soak_daily_report", payload["operator_warning_list"])
            self.assertIn("missing_artifact:paper_soak_review", payload["operator_warning_list"])
            self.assertIn("missing_artifact:paper_soak_review_history", payload["operator_warning_list"])
            self.assertIn("missing_artifact:paper_soak_status", payload["operator_warning_list"])
            self.assertIn("missing_artifact:paper_runtime_events", payload["operator_warning_list"])

    def test_stale_heartbeat_warning_surfaces_in_dashboard_telemetry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config = DummyConfig(tmpdir)
            _write_gate_artifacts(root)
            (root / "portfolio_status.json").write_text(json.dumps({"equity": 20000}), encoding="utf-8")
            (root / "paper_soak_status.json").write_text(
                json.dumps(
                    {
                        "classification": "paper-only",
                        "paper_runtime_allowed": True,
                        "real_money_allowed": False,
                        "last_heartbeat_timestamp": "2026-06-01T00:00:00+00:00",
                        "heartbeat": {"last_heartbeat_timestamp": "2026-06-01T00:00:00+00:00"},
                        "warning_list": [],
                    }
                ),
                encoding="utf-8",
            )

            payload = load_live_dashboard_snapshot(root, config=config)

            warning_blob = " / ".join(payload["paper_soak_status"].get("display_warning_list", []))
            self.assertIn("dashboard_detected_stale_heartbeat", warning_blob)
            self.assertIn("dashboard_detected_stale_heartbeat", " / ".join(payload["operator_warning_list"]))

    def test_build_trade_markers_creates_entry_and_exit_points(self):
        markers = build_trade_markers(
            [
                {
                    "symbol": "BTCUSDT",
                    "side": "short",
                    "entry_time": "2026-06-06 00:00:00",
                    "exit_time": "2026-06-06 01:00:00",
                    "pnl": "25.0",
                    "strategy_type": "h1_execution",
                }
            ],
            symbol="BTCUSDT",
        )
        self.assertEqual(2, len(markers))
        self.assertEqual("arrowDown", markers[0]["shape"])
        self.assertEqual("circle", markers[1]["shape"])

    def test_list_live_runs_prefers_root_live_output_with_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = DummyConfig(tmpdir)
            live_root = config.path("live_sim", "output_dir")
            live_root.mkdir(parents=True, exist_ok=True)
            (live_root / "engine_heartbeat.json").write_text(
                json.dumps({"cycle_count": 3}),
                encoding="utf-8",
            )
            (live_root / "portfolio_status.json").write_text(
                json.dumps({"equity": 10000}),
                encoding="utf-8",
            )
            log_dir = live_root / "cockpit_launcher_20260613_003459"
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "live_engine.stdout.log").write_text("ok", encoding="utf-8")

            rows = list_live_runs(config=config)

            self.assertEqual(1, len(rows))
            self.assertEqual(str(live_root), rows[0]["path"])

    def test_load_symbol_candles_prefers_live_runtime_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = DummyConfig(tmpdir)
            folder = config.path("storage", "base_path") / "BTCUSDT" / "1m"
            folder.mkdir(parents=True, exist_ok=True)
            historical_path = folder / "BTCUSDT_1m_2018-01-01_to_2026-05-12.csv"
            historical_path.write_text(
                "timestamp,open,high,low,close,volume\n"
                "2026-05-12 00:00:00,1,1,1,1,1\n",
                encoding="utf-8",
            )
            runtime_path = folder / "BTCUSDT_1m_live_runtime.csv"
            runtime_path.write_text(
                "timestamp,open,high,low,close,volume\n"
                "2026-06-13 00:00:00,2,2,2,2,2\n"
                "2026-06-13 00:01:00,3,3,3,3,3\n",
                encoding="utf-8",
            )

            payload = load_symbol_candles("BTCUSDT", timeframe="1m", limit=5, config=config)

            self.assertEqual(str(runtime_path), payload["source_path"])
            self.assertEqual(2, len(payload["candles"]))
            self.assertEqual(3.0, payload["candles"][-1]["close"])


if __name__ == "__main__":
    unittest.main()
