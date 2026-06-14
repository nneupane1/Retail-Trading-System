import csv
import json
import tempfile
import unittest
from pathlib import Path

from capital.phase1_diagnostics import (
    PHASE_1_DIAGNOSTICS,
    diagnostics_report_paths,
    write_phase1_diagnostics,
)
from config import AppConfig


def _base_config(root: Path) -> dict:
    return {
        "backtest": {"output_dir": str(root / "backtest" / "output")},
        "binance": {"ssl_verify": True, "ca_bundle_path": None},
        "live_sim": {
            "mode": "portfolio_paper",
            "output_dir": str(root / "live_output"),
            "paper_portfolio": {
                "allowed_sides": ["long"],
                "strategy_allowed_sides": {"h1_execution": ["short"]},
            },
        },
        "strategy": {
            "moonshots": {"swing": {"enabled": True}},
            "h1_execution": {"enabled": True},
            "htf_12h_standard": {"enabled": True},
            "htf_12h_moonshot": {"enabled": True},
            "htf_12h_rotation": {"enabled": True},
            "h6_standard": {"enabled": False},
            "h6_moonshot": {"enabled": False},
        },
        "capital_refactor": {
            "enabled": False,
            "capital_lanes": {"enabled": False},
            "risk_bands": {"enabled": False},
            "lifecycle": {"enabled": False},
            "opportunity_cost": {"enabled": False},
            "shadow_rejection_book": {"enabled": False},
            "winner_forensics": {"enabled": False},
            "capital_recycling": {"enabled": False},
            "regime_multiplier": {"enabled": False},
            "portfolio_heat": {"enabled": False},
            "promotion_review": {"enabled": False},
        },
    }


def _write_minimal_gate(root: Path) -> None:
    gate_root = root / "backtest" / "output" / "production_validation_gate_current"
    gate_root.mkdir(parents=True, exist_ok=True)
    scenario_full = gate_root / "scenario_current_routed_stack_full_history_latest_closed_day"
    scenario_holdout = gate_root / "scenario_current_routed_stack_trailing_12m_holdout"
    scenario_full.mkdir(parents=True, exist_ok=True)
    scenario_holdout.mkdir(parents=True, exist_ok=True)

    summary = {
        "latest_common_data_timestamp": "2026-06-13T00:00:00+00:00",
        "scenarios": {
            "full_history_latest_closed_day": {
                "name": scenario_full.name,
                "metrics": {"profit_factor": 1.2, "net_pnl": 500.0},
            },
            "trailing_12m_holdout": {
                "name": scenario_holdout.name,
                "metrics": {"profit_factor": 1.01, "net_pnl": 50.0},
            },
        },
    }
    report = {
        "real_money_ready": False,
        "blockers": [],
        "checks": [
            {"name": "full_history_positive_expectancy", "status": "pass", "passed": True},
            {"name": "holdout_positive_expectancy", "status": "pass", "passed": True},
        ],
    }
    status = {
        "stage": "complete",
        "summary_path": str(gate_root / "summary.json"),
        "promotion_readiness_report_path": str(gate_root / "promotion_readiness_report.json"),
        "real_money_ready": False,
        "blockers": [],
    }
    (gate_root / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (gate_root / "promotion_readiness_report.json").write_text(json.dumps(report), encoding="utf-8")
    (gate_root / "status.json").write_text(json.dumps(status), encoding="utf-8")

    for scenario_root in (scenario_full, scenario_holdout):
        (scenario_root / "validation_window.json").write_text(
            json.dumps({"window_policy": "fixture", "train_start": "2018-01-01"}),
            encoding="utf-8",
        )
        (scenario_root / "portfolio_status.json").write_text(
            json.dumps({"equity": 10100, "top_symbols": ["BTCUSDT"]}),
            encoding="utf-8",
        )
        (scenario_root / "trades.csv").write_text(
            "trade_id,symbol,side,entry_time,exit_time,pnl,pnl_R_total,score,score_bucket,strategy_type,regime_class,exit_reason,convexity_add_count\n"
            "t1,BTCUSDT,long,2026-06-01 00:00:00,2026-06-01 02:00:00,150.0,1.5,0.95,0.9-1.0,core,bullish,slow grind exit,0\n"
            "t2,ETHUSDT,short,2026-06-01 00:15:00,2026-06-01 03:15:00,-40.0,-0.5,0.88,0.8-0.9,h1_execution,bearish,stop,0\n",
            encoding="utf-8",
        )
        (scenario_root / "signals.csv").write_text(
            "timestamp,symbol,side,score,score_bucket,selected,selection_reason,strategy_type\n"
            "2026-06-01 00:00:00,BTCUSDT,long,0.95,0.9-1.0,True,opened,core\n"
            "2026-06-01 00:15:00,SOLUSDT,long,0.91,0.9-1.0,False,shared_risk_cap,core\n"
            "2026-06-01 00:30:00,ETHUSDT,short,0.73,0.7-0.8,False,score_bucket_filtered,h1_execution\n",
            encoding="utf-8",
        )
        (scenario_root / "allocator_decisions.csv").write_text(
            "timestamp,candidate_id,symbol,side,strategy_type,score,selection_score,score_bucket,allocation_rank,allocation_priority,final_reason,opened\n"
            "2026-06-01 00:00:00,0,BTCUSDT,long,core,0.95,0.95,0.9-1.0,1,0.9,opened,True\n"
            "2026-06-01 00:15:00,1,SOLUSDT,long,core,0.91,0.91,0.9-1.0,2,0.8,shared_risk_cap,False\n"
            "2026-06-01 00:30:00,2,ETHUSDT,short,h1_execution,0.73,0.73,0.7-0.8,1,0.7,score_bucket_filtered,False\n",
            encoding="utf-8",
        )


class CapitalDiagnosticsTests(unittest.TestCase):
    def _config(self, root: Path) -> AppConfig:
        config_dir = root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        settings_path = config_dir / "settings.json"
        settings_path.write_text(json.dumps(_base_config(root), indent=2), encoding="utf-8")
        return AppConfig.load(config_path=settings_path)

    def test_phase1_diagnostics_are_written_and_parseable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_minimal_gate(root)
            config = self._config(root)

            paths = write_phase1_diagnostics(
                config,
                readiness={
                    "classification": "paper-only",
                    "paper_runtime_allowed": True,
                    "real_money_allowed": False,
                },
            )

            for path in paths.values():
                self.assertTrue(path.exists(), str(path))

            with paths["rejection_shadow_book"].open("r", encoding="utf-8", newline="") as handle:
                rejection_rows = list(csv.DictReader(handle))
            self.assertGreaterEqual(len(rejection_rows), 2)

            with paths["capital_blocked_winners"].open("r", encoding="utf-8", newline="") as handle:
                blocked_rows = list(csv.DictReader(handle))
            self.assertEqual("shared_risk_cap", blocked_rows[0]["blocking_constraint"])

            with paths["top_winner_forensics"].open("r", encoding="utf-8", newline="") as handle:
                winner_rows = list(csv.DictReader(handle))
            self.assertEqual("t1", winner_rows[0]["trade_id"])

            efficiency_payload = json.loads(paths["strategy_bucket_capital_efficiency"].read_text(encoding="utf-8"))
            self.assertTrue(efficiency_payload["groups"])

            opportunity_payload = json.loads(paths["opportunity_cost_report"].read_text(encoding="utf-8"))
            self.assertTrue(opportunity_payload["observations"])

            summary_payload = json.loads(paths["diagnostics_summary"].read_text(encoding="utf-8"))
            self.assertEqual(PHASE_1_DIAGNOSTICS, summary_payload["phase"])
            self.assertFalse(summary_payload["behavior_change_allowed"])
            self.assertFalse(summary_payload["real_money_allowed"])
            self.assertFalse(summary_payload["allocator_behavior_changed"])
            self.assertFalse(summary_payload["risk_behavior_changed"])
            self.assertFalse(summary_payload["sizing_behavior_changed"])
            self.assertFalse(summary_payload["entry_behavior_changed"])
            self.assertFalse(summary_payload["exit_behavior_changed"])
            self.assertFalse(summary_payload["thresholds_changed"])
            self.assertFalse(summary_payload["sleeves_changed"])
            self.assertFalse(summary_payload["six_h_enabled"])
            self.assertTrue(summary_payload["h1_short_override_active"])
            self.assertIn("diagnostics_only_no_trading_behavior_change", summary_payload["warnings"])

    def test_diagnostics_report_paths_resolve_under_backtest_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._config(Path(temp_dir))
            paths = diagnostics_report_paths(config)

            self.assertTrue(str(paths["diagnostics_summary"]).endswith("backtest\\output\\capital_refactor\\diagnostics\\diagnostics_summary.json"))


if __name__ == "__main__":
    unittest.main()
