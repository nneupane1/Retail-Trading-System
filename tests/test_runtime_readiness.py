import json
import tempfile
import unittest
from pathlib import Path

from config import AppConfig
from common.runtime_readiness import (
    assert_runtime_mode_ready,
    build_runtime_readiness,
    ensure_official_gate_manifests,
)


def _base_config(root: Path, *, ssl_verify: bool) -> dict:
    return {
        "app": {"default_symbol": "BTCUSDT"},
        "backtest": {"output_dir": str(root / "backtest" / "output")},
        "binance": {
            "ssl_verify": ssl_verify,
            "ca_bundle_path": None,
        },
        "account": {"initial_equity": 20000, "risk_per_trade": 0.01},
        "live_sim": {
            "mode": "portfolio_paper",
            "output_dir": str(root / "live_sim" / "output"),
            "paper_portfolio": {
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


def _write_gate_artifacts(root: Path) -> None:
    gate_root = root / "backtest" / "output" / "production_validation_gate_current"
    gate_root.mkdir(parents=True, exist_ok=True)
    full_dir = gate_root / "scenario_current_routed_stack_full_history_latest_closed_day"
    holdout_dir = gate_root / "scenario_current_routed_stack_trailing_12m_holdout"
    full_dir.mkdir(parents=True, exist_ok=True)
    holdout_dir.mkdir(parents=True, exist_ok=True)
    status = {
        "stage": "complete",
        "summary_path": str(gate_root / "summary.json"),
        "promotion_readiness_report_path": str(gate_root / "promotion_readiness_report.json"),
        "real_money_ready": False,
        "blockers": ["binance_ssl_verify_enabled"],
    }
    validation_full = {
        "window_policy": "full_history_latest_closed_day_v1",
        "train_start": "2018-01-01",
        "train_end": "2026-06-13",
        "holdout_start": None,
        "holdout_end": None,
        "latest_data_timestamp": "2026-06-13T00:00:00+00:00",
        "resolved_at_utc": "2026-06-14T03:48:35.198556+00:00",
    }
    validation_holdout = {
        "window_policy": "trailing_12m_unseen_holdout_v1",
        "train_start": "2018-01-01",
        "train_end": "2025-06-13",
        "holdout_start": "2025-06-14",
        "holdout_end": "2026-06-13",
        "latest_data_timestamp": "2026-06-13T00:00:00+00:00",
        "resolved_at_utc": "2026-06-14T03:49:11.897995+00:00",
    }
    summary = {
        "latest_common_data_timestamp": "2026-06-13T00:00:00+00:00",
        "scenarios": {
            "full_history_latest_closed_day": {
                "name": "scenario_current_routed_stack_full_history_latest_closed_day",
                "output_dir": str(full_dir),
                "validation_window": validation_full,
                "metrics": {
                    "profit_factor": 1.26,
                    "net_pnl": 36365.20,
                    "avg_R": 0.022,
                    "median_daily_pnl": -0.77,
                },
            },
            "trailing_12m_holdout": {
                "name": "scenario_current_routed_stack_trailing_12m_holdout",
                "output_dir": str(holdout_dir),
                "validation_window": validation_holdout,
                "metrics": {
                    "profit_factor": 1.0217,
                    "net_pnl": 188.53,
                    "avg_R": -0.0060,
                    "median_daily_pnl": -0.767,
                },
            },
        },
    }
    report = {
        "real_money_ready": False,
        "passed": [
            "full_history_artifacts_complete",
            "full_history_positive_expectancy",
            "holdout_artifacts_complete",
            "holdout_positive_expectancy",
            "restart_restore_guarantees_present",
        ],
        "failed": [],
        "blockers": ["binance_ssl_verify_enabled"],
        "checks": [
            {"name": "full_history_artifacts_complete", "passed": True},
            {"name": "full_history_positive_expectancy", "passed": True},
            {"name": "holdout_artifacts_complete", "passed": True},
            {"name": "holdout_positive_expectancy", "passed": True},
            {"name": "restart_restore_guarantees_present", "passed": True},
        ],
    }
    (gate_root / "status.json").write_text(json.dumps(status), encoding="utf-8")
    (gate_root / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (gate_root / "promotion_readiness_report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )


class RuntimeReadinessTests(unittest.TestCase):
    def _config(self, root: Path, *, ssl_verify: bool) -> AppConfig:
        config_dir = root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        settings_path = config_dir / "settings.json"
        settings_path.write_text(
            json.dumps(_base_config(root, ssl_verify=ssl_verify), indent=2),
            encoding="utf-8",
        )
        return AppConfig.load(config_path=settings_path)

    def test_ssl_disabled_blocks_real_money_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_gate_artifacts(root)
            config = self._config(root, ssl_verify=False)

            with self.assertRaises(RuntimeError) as ctx:
                assert_runtime_mode_ready(config, mode="real_money")

            self.assertIn("ssl_verification_disabled", str(ctx.exception))

    def test_ssl_enabled_clears_specific_blocker_but_stays_paper_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_gate_artifacts(root)
            config = self._config(root, ssl_verify=True)

            readiness = build_runtime_readiness(config, mode="portfolio_paper")
            paper_readiness = assert_runtime_mode_ready(config, mode="portfolio_paper")

            self.assertNotIn("ssl_verification_disabled", readiness["blockers"])
            self.assertTrue(readiness["paper_runtime_allowed"])
            self.assertFalse(readiness["real_money_allowed"])
            self.assertEqual("paper-only", readiness["classification"])
            self.assertEqual("paper-only", paper_readiness["classification"])
            self.assertTrue(paper_readiness["paper_runtime_allowed"])

    def test_thin_but_passing_holdout_is_explicitly_paper_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_gate_artifacts(root)
            config = self._config(root, ssl_verify=True)

            readiness = build_runtime_readiness(config, mode="portfolio_paper")

            self.assertTrue(readiness["holdout_is_thin"])
            self.assertTrue(readiness["paper_runtime_allowed"])
            self.assertFalse(readiness["real_money_allowed"])
            self.assertEqual("paper-only", readiness["classification"])
            with self.assertRaises(RuntimeError) as ctx:
                assert_runtime_mode_ready(config, mode="real_money")
            self.assertIn("classification:paper-only", str(ctx.exception))

    def test_missing_gate_artifacts_blocks_real_money_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = self._config(root, ssl_verify=True)

            readiness = build_runtime_readiness(config, mode="real_money")

            self.assertIn("missing_status_json", readiness["blockers"])
            self.assertIn("missing_summary_json", readiness["blockers"])
            self.assertIn("missing_promotion_readiness_report_json", readiness["blockers"])
            self.assertFalse(readiness["real_money_allowed"])
            self.assertEqual("blocked", readiness["classification"])

    def test_scenario_manifests_are_written_with_required_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_gate_artifacts(root)
            config = self._config(root, ssl_verify=True)

            paths = ensure_official_gate_manifests(config)

            self.assertEqual(2, len(paths))
            manifest = json.loads(paths[0].read_text(encoding="utf-8"))
            self.assertIn("scenario_name", manifest)
            self.assertIn("run_entrypoint", manifest)
            self.assertIn("generated_at_utc", manifest)
            self.assertIn("current_universe_symbols", manifest)
            self.assertIn("active_sleeves", manifest)
            self.assertIn("disabled_sleeves", manifest)
            self.assertIn("allocator_settings", manifest)
            self.assertIn("key_risk_settings", manifest)
            self.assertIn("strategy_allowed_sides", manifest)
            self.assertIn("window_policy", manifest)
            self.assertIn("config_hashes", manifest)

    def test_runtime_config_marks_h6_disabled_and_h1_short_override_active(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_gate_artifacts(root)
            config = self._config(root, ssl_verify=True)

            readiness = build_runtime_readiness(config, mode="portfolio_paper")

            self.assertIn("h1_execution", readiness["runtime_config"]["active_sleeves"])
            self.assertIn("h6_standard", readiness["runtime_config"]["disabled_sleeves"])
            self.assertIn("h6_moonshot", readiness["runtime_config"]["disabled_sleeves"])
            self.assertEqual(
                ["short"],
                readiness["runtime_config"]["strategy_allowed_sides"]["h1_execution"],
            )


if __name__ == "__main__":
    unittest.main()
