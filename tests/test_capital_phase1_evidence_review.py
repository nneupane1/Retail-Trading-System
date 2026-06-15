import json
import tempfile
import unittest
from pathlib import Path

from capital.phase1_diagnostics import write_phase1_diagnostics
from capital.phase1_evidence_review import (
    PHASE_1_EVIDENCE_REVIEW,
    review_report_paths,
    write_phase1_evidence_review,
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


class CapitalPhase1EvidenceReviewTests(unittest.TestCase):
    def _config(self, root: Path) -> AppConfig:
        config_dir = root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        settings_path = config_dir / "settings.json"
        settings_path.write_text(json.dumps(_base_config(root), indent=2), encoding="utf-8")
        return AppConfig.load(config_path=settings_path)

    def test_review_is_written_and_parseable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_minimal_gate(root)
            config = self._config(root)
            write_phase1_diagnostics(config)

            paths = write_phase1_evidence_review(config)

            for path in paths.values():
                self.assertTrue(path.exists(), str(path))

            payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(PHASE_1_EVIDENCE_REVIEW, payload["phase"])
            self.assertFalse(payload["behavior_change_allowed"])
            self.assertFalse(payload["real_money_allowed"])
            self.assertFalse(payload["allocator_behavior_changed"])
            self.assertFalse(payload["risk_behavior_changed"])
            self.assertFalse(payload["sizing_behavior_changed"])
            self.assertFalse(payload["entry_behavior_changed"])
            self.assertFalse(payload["exit_behavior_changed"])
            self.assertFalse(payload["thresholds_changed"])
            self.assertFalse(payload["sleeves_changed"])
            self.assertFalse(payload["six_h_enabled"])
            self.assertTrue(payload["h1_short_override_active"])
            self.assertIn("top_rejection_reasons", payload)
            self.assertIn("phase2_not_allowed_yet_reasoning", payload)
            self.assertGreaterEqual(payload["data_quality"]["rejection_shadow_book"]["rows_with_hypothetical_support"], 0)

            markdown_text = paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("Executive summary", markdown_text)
            self.assertIn("Confirmation no behavior changed", markdown_text)

            brief_text = paths["phase2_brief"].read_text(encoding="utf-8")
            self.assertIn("backtest-only first", brief_text)
            self.assertIn("must not touch live paper runtime initially", brief_text)

    def test_review_resumes_from_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_minimal_gate(root)
            config = self._config(root)
            write_phase1_diagnostics(config)
            paths = write_phase1_evidence_review(config)

            initial_payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            review_progress = json.loads(paths["progress"].read_text(encoding="utf-8"))
            self.assertIn("json", review_progress["completed_steps"])

            paths["markdown"].unlink()

            rerun_paths = write_phase1_evidence_review(config)
            rerun_payload = json.loads(rerun_paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(initial_payload["generated_at_utc"], rerun_payload["generated_at_utc"])
            self.assertTrue(rerun_paths["markdown"].exists())

    def test_review_report_paths_resolve_under_review_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._config(Path(temp_dir))
            paths = review_report_paths(config)

            self.assertTrue(str(paths["json"]).endswith("backtest\\output\\capital_refactor\\diagnostics\\review\\phase1_evidence_review.json"))


if __name__ == "__main__":
    unittest.main()
