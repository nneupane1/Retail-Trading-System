import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from live_sim.runner import (
    _append_paper_runtime_event,
    _append_paper_soak_review_history,
    _baseline_freeze_snapshot_path,
    _build_baseline_freeze_snapshot,
    _manual_review_outcome_from_soak_review,
    _build_paper_soak_daily_report,
    _build_paper_soak_review,
    _build_paper_soak_status,
    _build_paper_soak_warnings,
    _discover_live_symbols,
    _load_live_bootstrap_history,
    _load_live_portfolio_snapshot,
    _momentum_ranks,
    _merge_recent_into_state,
    _paper_runtime_startup_report_path,
    _paper_runtime_events_path,
    _paper_soak_daily_report_path,
    _paper_soak_review_history_path,
    _paper_soak_review_path,
    _paper_soak_status_path,
    _portfolio_runtime_state_path,
    _required_live_warmup_minutes,
    _runtime_state_path,
    _write_paper_soak_daily_report,
    _write_baseline_freeze_snapshot,
    _write_paper_soak_review,
    _write_paper_soak_status,
    _write_paper_runtime_startup_report,
)


class DummyConfig:
    def __init__(self, storage_base_path):
        root_dir = Path(storage_base_path).parent
        self.config_path = root_dir / "config" / "settings.json"
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            self.config_path.write_text("{}", encoding="utf-8")
        self.data = {
            "app": {
                "default_symbol": "BTCUSDT",
            },
            "binance": {
                "default_interval": "1m",
                "recent_limit": 1000,
            },
            "live_sim": {
                "poll_seconds": 30,
                "output_dir": str(Path(storage_base_path).parent / "live_output"),
                "universe": {
                    "symbols": ["BTCUSDT", "ETHUSDT"],
                    "active_set": "current_9",
                },
            },
            "storage": {
                "base_path": storage_base_path,
            },
            "history": {
                "start_date": "2018-01-01",
                "end_date": "2026-05-12",
            },
            "paper_soak": {
                "minimum_days_before_review": 14,
            },
            "downloads": {
                "history": {
                    "partial_suffix": ".partial.csv",
                },
            },
            "universe": {
                "active_set": "current_9",
                "symbol_sets": {
                    "current_9": ["BTCUSDT", "ETHUSDT"],
                    "expanded_liquid_28": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
                },
            },
            "features": {
                "ema_periods": {
                    "fast": 20,
                    "slow": 50,
                },
                "structure": {
                    "high_period": 20,
                    "low_period": 10,
                },
                "compression": {
                    "slow_range_period": 30,
                },
                "candle_metrics": {
                    "average_body_period": 10,
                },
            },
            "strategy": {
                "bias": {
                    "ema_column": "ema50",
                    "slope_lookback": 3,
                },
                "regime": {
                    "ema_column": "ema50",
                    "slope_lookback": 5,
                },
            },
            "timeframes": {
                "execution": {"rule": "15min"},
                "direction": {"rule": "1h"},
                "trend": {"rule": "5h"},
                "macro": {"rule": "12h"},
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


class LiveSimRunnerTests(unittest.TestCase):
    def test_discover_live_symbols_uses_local_symbol_folders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "BTCUSDT").mkdir(parents=True, exist_ok=True)
            Path(temp_dir, "ETHUSDT").mkdir(parents=True, exist_ok=True)
            config = DummyConfig(storage_base_path=temp_dir)

            symbols = _discover_live_symbols(config)

            self.assertEqual(symbols, ["BTCUSDT", "ETHUSDT"])

    def test_discover_live_symbols_can_use_named_universe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=temp_dir)
            config.data["live_sim"]["universe"]["symbols"] = []
            config.data["live_sim"]["universe"]["active_set"] = "expanded_liquid_28"

            symbols = _discover_live_symbols(config)

            self.assertEqual(symbols, ["BTCUSDT", "ETHUSDT", "SOLUSDT"])

    def test_required_live_warmup_minutes_covers_macro_requirement(self):
        config = DummyConfig(storage_base_path="data_storage")

        warmup_minutes = _required_live_warmup_minutes(config)

        self.assertEqual(warmup_minutes, 46800)

    def test_merge_recent_into_state_deduplicates_and_keeps_latest_rows(self):
        index_existing = pd.to_datetime([
            "2026-01-01 00:00:00",
            "2026-01-01 00:01:00",
        ])
        existing = pd.DataFrame(
            {
                "open": [1, 2],
                "high": [1, 2],
                "low": [1, 2],
                "close": [1, 2],
                "volume": [10, 20],
            },
            index=index_existing,
        )

        index_recent = pd.to_datetime([
            "2026-01-01 00:01:00",
            "2026-01-01 00:02:00",
        ])
        recent = pd.DataFrame(
            {
                "open": [20, 30],
                "high": [20, 30],
                "low": [20, 30],
                "close": [20, 30],
                "volume": [200, 300],
            },
            index=index_recent,
        )

        merged = _merge_recent_into_state(existing, recent, warmup_minutes=60)

        self.assertEqual(len(merged), 3)
        self.assertEqual(merged.loc[pd.Timestamp("2026-01-01 00:01:00"), "close"], 20)
        self.assertEqual(merged.index[-1], pd.Timestamp("2026-01-01 00:02:00"))

    def test_load_live_bootstrap_history_prefers_final_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=temp_dir)
            folder = Path(temp_dir) / "BTCUSDT" / "1m"
            folder.mkdir(parents=True, exist_ok=True)

            final_path = folder / "BTCUSDT_1m_2018-01-01_to_2026-05-12.csv"
            partial_path = folder / "BTCUSDT_1m_2018-01-01_to_2026-05-12.csv.partial.csv"

            final_path.write_text(
                "timestamp,open,high,low,close,volume\n"
                "2026-01-01 00:00:00,1,1,1,1,1\n"
                "2026-01-01 00:01:00,2,2,2,2,2\n"
                "2026-01-01 00:02:00,3,3,3,3,3\n",
                encoding="utf-8",
            )
            partial_path.write_text(
                "timestamp,open,high,low,close,volume\n"
                "2026-01-01 00:00:00,9,9,9,9,9\n",
                encoding="utf-8",
            )

            df_1m, source_path = _load_live_bootstrap_history(
                symbol="BTCUSDT",
                interval="1m",
                warmup_minutes=60,
                config=config,
            )

            self.assertEqual(source_path, final_path)
            self.assertEqual(len(df_1m), 3)
            self.assertEqual(df_1m["close"].iloc[-1], 3)

    def test_load_live_bootstrap_history_falls_back_to_partial_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=temp_dir)
            folder = Path(temp_dir) / "BTCUSDT" / "1m"
            folder.mkdir(parents=True, exist_ok=True)

            partial_path = folder / "BTCUSDT_1m_2018-01-01_to_2026-05-12.csv.partial.csv"
            partial_path.write_text(
                "timestamp,open,high,low,close,volume\n"
                "2026-01-01 00:00:00,1,1,1,1,1\n"
                "2026-01-01 00:01:00,2,2,2,2,2\n",
                encoding="utf-8",
            )

            df_1m, source_path = _load_live_bootstrap_history(
                symbol="BTCUSDT",
                interval="1m",
                warmup_minutes=60,
                config=config,
            )

            self.assertEqual(source_path, partial_path)
            self.assertEqual(len(df_1m), 2)

    def test_load_live_bootstrap_history_can_use_timestamped_storage_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=temp_dir)
            folder = Path(temp_dir) / "BTCUSDT" / "1m"
            folder.mkdir(parents=True, exist_ok=True)

            timestamped = folder / (
                "BTCUSDT_1m_2018-01-01T00.00.00_to_2026-05-23T00.00.00.csv"
            )
            timestamped.write_text(
                "timestamp,open,high,low,close,volume\n"
                "2026-01-01 00:00:00,1,1,1,1,1\n"
                "2026-01-01 00:01:00,2,2,2,2,2\n",
                encoding="utf-8",
            )

            df_1m, source_path = _load_live_bootstrap_history(
                symbol="BTCUSDT",
                interval="1m",
                warmup_minutes=60,
                config=config,
            )

            self.assertEqual(source_path, timestamped)
            self.assertEqual(len(df_1m), 2)

    def test_load_live_bootstrap_history_accepts_later_starting_timestamped_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=temp_dir)
            folder = Path(temp_dir) / "SUIUSDT" / "1m"
            folder.mkdir(parents=True, exist_ok=True)

            timestamped = folder / (
                "SUIUSDT_1m_2023-05-01T00.00.00_to_2026-05-23T00.00.00.csv"
            )
            timestamped.write_text(
                "timestamp,open,high,low,close,volume\n"
                "2026-01-01 00:00:00,1,1,1,1,1\n"
                "2026-01-01 00:01:00,2,2,2,2,2\n",
                encoding="utf-8",
            )

            df_1m, source_path = _load_live_bootstrap_history(
                symbol="SUIUSDT",
                interval="1m",
                warmup_minutes=60,
                config=config,
            )

            self.assertEqual(source_path, timestamped)
            self.assertEqual(len(df_1m), 2)

    def test_load_live_bootstrap_history_prefers_runtime_state_when_present(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=temp_dir)
            folder = Path(temp_dir) / "BTCUSDT" / "1m"
            folder.mkdir(parents=True, exist_ok=True)

            final_path = folder / "BTCUSDT_1m_2018-01-01_to_2026-05-12.csv"
            final_path.write_text(
                "timestamp,open,high,low,close,volume\n"
                "2026-05-12 00:00:00,1,1,1,1,1\n"
                "2026-05-12 00:01:00,2,2,2,2,2\n",
                encoding="utf-8",
            )
            runtime_path = _runtime_state_path("BTCUSDT", "1m", config)
            runtime_path.write_text(
                "timestamp,open,high,low,close,volume\n"
                "2026-06-13 00:00:00,5,5,5,5,5\n"
                "2026-06-13 00:01:00,6,6,6,6,6\n",
                encoding="utf-8",
            )

            df_1m, source_path = _load_live_bootstrap_history(
                symbol="BTCUSDT",
                interval="1m",
                warmup_minutes=60 * 24 * 60,
                config=config,
            )

            self.assertEqual(source_path, runtime_path)
            self.assertEqual(df_1m.index[-1], pd.Timestamp("2026-06-13 00:01:00"))
            self.assertEqual(df_1m["close"].iloc[-1], 6)

    def test_load_live_portfolio_snapshot_uses_only_live_output_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=Path(temp_dir) / "data_storage")
            live_snapshot_path = _portfolio_runtime_state_path(config)
            live_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            backtest_snapshot_path = (
                Path(temp_dir)
                / "backtest"
                / "output"
                / "production_validation_gate_current"
                / "scenario_current_routed_stack_trailing_12m_holdout"
                / "portfolio_runtime_state.json"
            )
            backtest_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            backtest_snapshot_path.write_text(
                '{"open_positions":[{"symbol":"BTCUSDT"}]}',
                encoding="utf-8",
            )

            payload, source_path = _load_live_portfolio_snapshot(config)

            self.assertIsNone(payload)
            self.assertEqual(source_path, live_snapshot_path)

    def test_load_live_portfolio_snapshot_restores_only_live_state_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=Path(temp_dir) / "data_storage")
            live_snapshot_path = _portfolio_runtime_state_path(config)
            live_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            live_snapshot_path.write_text(
                '{"open_positions":[{"symbol":"BTCUSDT"}],"runtime_context":{"mode":"portfolio_paper"}}',
                encoding="utf-8",
            )

            payload, source_path = _load_live_portfolio_snapshot(config)

            self.assertEqual(source_path, live_snapshot_path)
            self.assertEqual("BTCUSDT", payload["open_positions"][0]["symbol"])
            self.assertEqual("portfolio_paper", payload["runtime_context"]["mode"])

    def test_paper_runtime_startup_report_is_written_and_parseable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=Path(temp_dir) / "data_storage")
            payload = {
                "classification": "paper-only",
                "paper_runtime_allowed": True,
                "real_money_allowed": False,
                "blockers": [],
                "validated_boundary": "2026-06-13T00:00:00+00:00",
                "runtime_first_processed_candle": "2026-06-13T00:01:00+00:00",
                "runtime_last_processed_candle": "2026-06-14T00:00:00+00:00",
                "restored_state_used": False,
                "restored_positions_count": 0,
                "active_sleeves": ["core", "h1_execution", "htf_12h_standard"],
                "disabled_sleeves": ["h6_standard", "h6_moonshot"],
                "allowed_sides": ["long"],
                "strategy_allowed_sides": {"h1_execution": ["short"]},
                "ssl_verify": True,
            }

            report_path = _write_paper_runtime_startup_report(config, payload)

            self.assertEqual(report_path, _paper_runtime_startup_report_path(config))
            self.assertTrue(report_path.exists())
            parsed = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual("paper-only", parsed["classification"])
            self.assertFalse(parsed["real_money_allowed"])

    def test_paper_soak_status_is_written_and_parseable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=Path(temp_dir) / "data_storage")
            portfolio = SimpleNamespace(
                open_positions=[],
                account=SimpleNamespace(equity=20100.0),
                daily_entries_taken=3,
                daily_closed_trades=2,
                daily_closed_pnl=125.0,
                daily_loss_streak=1,
                strategy_stats={"core": {"count": 5, "total_pnl": 80.0}},
            )
            readiness = {
                "classification": "paper-only",
                "paper_runtime_allowed": True,
                "real_money_allowed": False,
                "tls": {"ssl_verify": True},
                "validated_boundary": "2026-06-13T00:00:00+00:00",
                "warnings": [],
                "blockers": [],
                "runtime_config": {
                    "active_sleeves": ["core", "h1_execution"],
                    "disabled_sleeves": ["h6_standard", "h6_moonshot"],
                    "allowed_sides": ["long"],
                    "strategy_allowed_sides": {"h1_execution": ["short"]},
                },
            }
            heartbeat = {
                "poll_seconds": 30.0,
                "last_heartbeat_timestamp": "2099-01-01T00:00:00+00:00",
            }
            payload = _build_paper_soak_status(
                readiness=readiness,
                portfolio=portfolio,
                runtime_started_at="2026-06-14T00:00:00+00:00",
                runtime_last_processed_timestamp="2099-01-01T00:00:00+00:00",
                restored_state_used=False,
                restored_positions_count=0,
                latest_prices={},
                selection_summary={"final_reason_counts": {"opened": 1, "shared_risk_cap": 2}},
                heartbeat_payload=heartbeat,
                runtime_start_equity=20000.0,
            )

            status_path = _write_paper_soak_status(config, payload)

            self.assertEqual(status_path, _paper_soak_status_path(config))
            parsed = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual("paper-only", parsed["classification"])
            self.assertTrue(parsed["paper_runtime_allowed"])
            self.assertFalse(parsed["real_money_allowed"])
            self.assertEqual(100.0, parsed["realized_paper_pnl_since_runtime_start"])
            self.assertEqual({"shared_risk_cap": 2}, parsed["latest_allocator_rejection_counts"])

    def test_paper_soak_daily_report_is_written_and_parseable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=Path(temp_dir) / "data_storage")
            portfolio = SimpleNamespace(
                open_positions=[],
                account=SimpleNamespace(equity=20150.0),
                daily_entries_taken=4,
                daily_closed_trades=2,
                daily_closed_pnl=90.0,
                daily_loss_streak=1,
                strategy_stats={
                    "core": {"count": 5, "wins": 3, "total_pnl": 80.0},
                    "h1_execution": {"count": 2, "wins": 1, "total_pnl": 15.0},
                },
                selection_reason_counts_by_strategy={
                    "core": {"opened": 3, "shared_risk_cap": 2},
                    "h1_execution": {"opened": 1, "strategy_health_filtered": 1},
                },
            )
            readiness = {
                "classification": "paper-only",
                "paper_runtime_allowed": True,
                "real_money_allowed": False,
                "holdout_is_thin": True,
                "tls": {"ssl_verify": True},
                "validated_boundary": "2026-06-13T00:00:00+00:00",
                "warnings": [],
                "blockers": [],
                "runtime_config": {
                    "active_sleeves": ["core", "swing_moonshot", "h1_execution", "htf_12h_standard", "htf_12h_moonshot", "htf_12h_rotation"],
                    "disabled_sleeves": ["h6_standard", "h6_moonshot"],
                    "allowed_sides": ["long"],
                    "strategy_allowed_sides": {"h1_execution": ["short"]},
                },
            }
            soak_status = _build_paper_soak_status(
                readiness=readiness,
                portfolio=portfolio,
                runtime_started_at="2026-06-14T00:00:00+00:00",
                runtime_last_processed_timestamp="2099-01-01T00:00:00+00:00",
                restored_state_used=True,
                restored_positions_count=0,
                latest_prices={},
                selection_summary={"final_reason_counts": {"opened": 2, "shared_risk_cap": 3, "direction_cap": 1}},
                heartbeat_payload={
                    "poll_seconds": 30.0,
                    "last_heartbeat_timestamp": "2099-01-01T00:00:00+00:00",
                },
                runtime_start_equity=20000.0,
            )
            startup_report = {
                "runtime_mode": "portfolio_paper",
                "runtime_start_timestamp": "2026-06-14T00:00:00+00:00",
                "restored_state_path": "live_sim\\output\\portfolio_runtime_state.json",
                "restored_positions_count": 0,
            }
            _append_paper_runtime_event(
                config,
                {"startup_time": "2026-06-14T00:00:00+00:00", "restore_happened": True},
            )

            payload = _build_paper_soak_daily_report(
                readiness=readiness,
                portfolio=portfolio,
                soak_status=soak_status,
                startup_report=startup_report,
                latest_prices={},
                selection_summary={"final_reason_counts": {"opened": 2, "shared_risk_cap": 3, "direction_cap": 1}},
                event_log_path=_paper_runtime_events_path(config),
            )
            report_path = _write_paper_soak_daily_report(config, payload)

            self.assertEqual(report_path, _paper_soak_daily_report_path(config))
            parsed = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual("paper_soak_in_progress", parsed["promotion_criteria"]["promotion_status"])
            self.assertFalse(parsed["real_money_allowed"])
            self.assertEqual(["h6_standard", "h6_moonshot"], parsed["disabled_sleeves"])
            self.assertTrue(parsed["h1_short_override_active"])
            self.assertTrue(parsed["h6_disabled_status"])
            self.assertEqual(0, parsed["h6_route_counts"]["h6_standard"])
            self.assertEqual(0, parsed["h6_route_counts"]["h6_moonshot"])
            self.assertEqual(3, parsed["allocator_decision_counts"]["shared_risk_cap"])
            self.assertIn("core", parsed["strategy_daily_evidence"])
            self.assertIn("h1_execution", parsed["strategy_daily_evidence"])

    def test_paper_soak_daily_report_handles_missing_optional_stats(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=Path(temp_dir) / "data_storage")
            portfolio = SimpleNamespace(
                open_positions=[],
                account=SimpleNamespace(equity=20000.0),
                daily_entries_taken=0,
                daily_closed_trades=0,
                daily_closed_pnl=0.0,
                daily_loss_streak=0,
            )
            soak_status = {
                "classification": "paper-only",
                "paper_runtime_allowed": True,
                "real_money_allowed": False,
                "ssl_verify": True,
                "validated_boundary": "2026-06-13T00:00:00+00:00",
                "runtime_started_at": "2026-06-14T00:00:00+00:00",
                "runtime_last_processed_timestamp": "2026-06-14T00:15:00+00:00",
                "runtime_uptime_seconds": 60.0,
                "current_paper_equity": 20000.0,
                "paper_start_equity": 20000.0,
                "realized_paper_pnl_since_runtime_start": 0.0,
                "unrealized_paper_pnl": 0.0,
                "daily_entries": 0,
                "daily_closed_trades": 0,
                "daily_closed_pnl": 0.0,
                "active_sleeves": ["core"],
                "disabled_sleeves": ["h6_standard", "h6_moonshot"],
                "h1_short_override_active": True,
                "h6_routes_zero_trades_expected": True,
                "warning_list": [],
                "blocker_list": [],
                "restored_state_used": False,
                "restored_positions_count": 0,
                "last_heartbeat_timestamp": "2026-06-14T00:15:00+00:00",
            }
            payload = _build_paper_soak_daily_report(
                readiness={"holdout_is_thin": True},
                portfolio=portfolio,
                soak_status=soak_status,
                startup_report={},
                latest_prices={},
                selection_summary={"final_reason_counts": {}},
                event_log_path=_paper_runtime_events_path(config),
            )

            self.assertEqual("paper_soak_in_progress", payload["promotion_criteria"]["promotion_status"])
            self.assertEqual(0, payload["allocator_decision_counts"]["shared_risk_cap"])
            self.assertIn("core", payload["strategy_daily_evidence"])

    def test_paper_soak_review_is_written_and_parseable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=Path(temp_dir) / "data_storage")
            portfolio = SimpleNamespace(
                open_positions=[],
                account=SimpleNamespace(equity=20150.0),
                daily_entries_taken=2,
                daily_closed_trades=1,
                daily_closed_pnl=45.0,
                daily_loss_streak=0,
                strategy_stats={
                    "core": {"count": 3, "wins": 2, "total_pnl": 55.0},
                    "h1_execution": {"count": 1, "wins": 1, "total_pnl": 15.0},
                },
                selection_reason_counts_by_strategy={
                    "core": {"opened": 2},
                    "h1_execution": {"opened": 1},
                },
            )
            readiness = {
                "classification": "paper-only",
                "paper_runtime_allowed": True,
                "real_money_allowed": False,
                "holdout_is_thin": True,
                "tls": {"ssl_verify": True},
                "validated_boundary": "2026-06-13T00:00:00+00:00",
                "warnings": [],
                "blockers": [],
                "runtime_config": {
                    "active_sleeves": ["core", "swing_moonshot", "h1_execution", "htf_12h_standard", "htf_12h_moonshot", "htf_12h_rotation"],
                    "disabled_sleeves": ["h6_standard", "h6_moonshot"],
                    "allowed_sides": ["long"],
                    "strategy_allowed_sides": {"h1_execution": ["short"]},
                },
            }
            soak_status = _build_paper_soak_status(
                readiness=readiness,
                portfolio=portfolio,
                runtime_started_at="2026-06-14T00:00:00+00:00",
                runtime_last_processed_timestamp="2099-01-01T00:00:00+00:00",
                restored_state_used=True,
                restored_positions_count=0,
                latest_prices={},
                selection_summary={"final_reason_counts": {"opened": 2, "shared_risk_cap": 1}},
                heartbeat_payload={
                    "poll_seconds": 30.0,
                    "last_heartbeat_timestamp": "2099-01-01T00:00:00+00:00",
                },
                runtime_start_equity=20000.0,
            )
            startup_report = {
                "runtime_mode": "portfolio_paper",
                "runtime_start_timestamp": "2026-06-14T00:00:00+00:00",
                "restored_state_path": str(_portfolio_runtime_state_path(config)),
                "restored_positions_count": 0,
            }
            _append_paper_runtime_event(
                config,
                {"startup_time": "2026-06-14T00:00:00+00:00", "restore_happened": True},
            )
            _portfolio_runtime_state_path(config).parent.mkdir(parents=True, exist_ok=True)
            _portfolio_runtime_state_path(config).write_text(
                json.dumps({"open_positions": [], "runtime_context": {"restored_state_path": str(_portfolio_runtime_state_path(config))}}),
                encoding="utf-8",
            )
            (Path(config.require("live_sim", "output_dir")) / "portfolio_status.json").write_text(
                json.dumps({"equity": 20150.0, "open_positions": 0, "top_symbols": ["BTCUSDT"]}),
                encoding="utf-8",
            )
            (Path(config.require("live_sim", "output_dir")) / "daily_summary.csv").write_text(
                "date,equity_start,equity_end,realized_pnl,realized_return_fraction,entries_taken,closed_trades,threshold\n"
                "2026-06-13,20000,20050,50,0.0025,1,1,0.82\n"
                "2026-06-14,20050,20150,100,0.0049,2,1,0.82\n",
                encoding="utf-8",
            )

            daily_report = _build_paper_soak_daily_report(
                readiness=readiness,
                portfolio=portfolio,
                soak_status=soak_status,
                startup_report=startup_report,
                latest_prices={},
                selection_summary={"final_reason_counts": {"opened": 2, "shared_risk_cap": 1}},
                event_log_path=_paper_runtime_events_path(config),
            )
            review_payload = _build_paper_soak_review(
                config=config,
                readiness=readiness,
                soak_status=soak_status,
                daily_report=daily_report,
                startup_report=startup_report,
                event_log_path=_paper_runtime_events_path(config),
            )
            review_path = _write_paper_soak_review(config, review_payload)

            self.assertEqual(review_path, _paper_soak_review_path(config))
            parsed = json.loads(review_path.read_text(encoding="utf-8"))
            self.assertEqual("insufficient_forward_paper_duration", parsed["soak_review_status"])
            self.assertFalse(parsed["real_money_allowed"])
            self.assertEqual(14, parsed["required_soak_days"])
            self.assertEqual("pass", parsed["soak_review_criteria"]["h6_routes_zero_trades"]["status"])
            self.assertEqual("pass", parsed["soak_review_criteria"]["h1_short_override_active"]["status"])

    def test_paper_soak_review_history_appends(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=Path(temp_dir) / "data_storage")
            first = {
                "review_generated_at_utc": "2026-06-14T00:00:00+00:00",
                "soak_days_completed": 0.5,
                "current_paper_equity": 20050.0,
                "realized_pnl_since_paper_start": 50.0,
                "max_paper_drawdown_fraction": 0.01,
                "blocker_list": [],
                "warning_list": ["holdout_edge_thin"],
                "soak_review_status": "insufficient_forward_paper_duration",
            }
            second = {
                "review_generated_at_utc": "2026-06-15T00:00:00+00:00",
                "soak_days_completed": 1.5,
                "current_paper_equity": 20125.0,
                "realized_pnl_since_paper_start": 125.0,
                "max_paper_drawdown_fraction": 0.02,
                "blocker_list": [],
                "warning_list": [],
                "soak_review_status": "insufficient_forward_paper_duration",
            }

            history_path = _append_paper_soak_review_history(config, first)
            _append_paper_soak_review_history(config, second)

            self.assertEqual(history_path, _paper_soak_review_history_path(config))
            rows = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(2, len(rows))
            self.assertEqual("2026-06-14T00:00:00+00:00", rows[0]["timestamp"])
            self.assertEqual(1.5, rows[1]["soak_days_completed"])

    def test_paper_soak_review_handles_missing_optional_stats(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=Path(temp_dir) / "data_storage")
            config.data["paper_soak"]["minimum_days_before_review"] = 30
            readiness = {
                "classification": "paper-only",
                "paper_runtime_allowed": True,
                "real_money_allowed": False,
                "holdout_is_thin": True,
                "tls": {"ssl_verify": True},
                "validated_boundary": "2026-06-13T00:00:00+00:00",
                "warnings": [],
                "blockers": [],
                "runtime_config": {
                    "active_sleeves": ["core", "h1_execution"],
                    "disabled_sleeves": ["h6_standard", "h6_moonshot"],
                    "allowed_sides": ["long"],
                    "strategy_allowed_sides": {"h1_execution": ["short"]},
                },
            }
            soak_status = {
                "classification": "paper-only",
                "paper_runtime_allowed": True,
                "real_money_allowed": False,
                "ssl_verify": True,
                "validated_boundary": "2026-06-13T00:00:00+00:00",
                "runtime_started_at": "2026-06-14T00:00:00+00:00",
                "runtime_last_processed_timestamp": "2026-06-14T00:15:00+00:00",
                "runtime_uptime_seconds": 3600.0,
                "current_paper_equity": 20000.0,
                "paper_start_equity": 20000.0,
                "realized_paper_pnl_since_runtime_start": 0.0,
                "unrealized_paper_pnl": 0.0,
                "active_sleeves": ["core", "h1_execution"],
                "disabled_sleeves": ["h6_standard", "h6_moonshot"],
                "warning_list": [],
                "blocker_list": [],
            }
            daily_report = {
                "classification": "paper-only",
                "paper_runtime_allowed": True,
                "real_money_allowed": False,
                "ssl_verify": True,
                "runtime_last_processed_timestamp": "2026-06-14T00:15:00+00:00",
                "heartbeat_status": "healthy",
                "stale_warnings": [],
                "current_paper_equity": 20000.0,
                "realized_pnl_since_paper_start": 0.0,
                "unrealized_pnl": 0.0,
                "open_positions": 0,
                "active_sleeves": ["core", "h1_execution"],
                "disabled_sleeves": ["h6_standard", "h6_moonshot"],
                "h1_short_override_active": True,
                "h6_disabled_status": True,
                "h6_route_counts": {"h6_standard": 0, "h6_moonshot": 0},
                "warning_list": [],
                "blocker_list": [],
                "allocator_rejection_counts": {},
                "allocator_decision_counts": {},
                "strategy_daily_evidence": {},
                "restored_state_used": False,
                "restored_positions_count": 0,
            }
            startup_report = {
                "restored_state_path": str(_portfolio_runtime_state_path(config)),
                "runtime_start_timestamp": "2026-06-14T00:00:00+00:00",
            }
            _portfolio_runtime_state_path(config).parent.mkdir(parents=True, exist_ok=True)
            _portfolio_runtime_state_path(config).write_text(json.dumps({"open_positions": []}), encoding="utf-8")
            (Path(config.require("live_sim", "output_dir")) / "portfolio_status.json").write_text(
                json.dumps({"equity": 20000.0}),
                encoding="utf-8",
            )

            review_payload = _build_paper_soak_review(
                config=config,
                readiness=readiness,
                soak_status=soak_status,
                daily_report=daily_report,
                startup_report=startup_report,
                event_log_path=_paper_runtime_events_path(config),
            )

            self.assertEqual("insufficient_forward_paper_duration", review_payload["soak_review_status"])
            self.assertFalse(review_payload["real_money_allowed"])
            self.assertEqual(30, review_payload["required_soak_days"])
            self.assertIsNone(review_payload["max_paper_drawdown_fraction"])
            self.assertEqual("pass", review_payload["soak_review_criteria"]["h6_routes_zero_trades"]["status"])
            self.assertEqual("pass", review_payload["soak_review_criteria"]["h1_short_override_active"]["status"])

    def test_baseline_freeze_snapshot_is_written_and_parseable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=Path(temp_dir) / "data_storage")
            readiness = {
                "classification": "paper-only",
                "paper_runtime_allowed": True,
                "real_money_allowed": False,
                "tls": {"ssl_verify": True},
                "validated_boundary": "2026-06-13T00:00:00+00:00",
                "summary_path": str(Path(temp_dir) / "backtest" / "output" / "production_validation_gate_current" / "summary.json"),
                "promotion_readiness_report_path": str(Path(temp_dir) / "backtest" / "output" / "production_validation_gate_current" / "promotion_readiness_report.json"),
                "gate_root": str(Path(temp_dir) / "backtest" / "output" / "production_validation_gate_current"),
                "scenario_manifest_paths": {"full_history": "manifest_a.json"},
                "runtime_config": {
                    "active_sleeves": ["core", "h1_execution"],
                    "disabled_sleeves": ["h6_standard", "h6_moonshot"],
                },
            }
            startup_report = {
                "runtime_mode": "portfolio_paper",
                "generated_at_utc": "2026-06-14T00:00:00+00:00",
            }
            daily_report = {
                "promotion_criteria": {"promotion_status": "paper_soak_in_progress"},
            }
            soak_review = {
                "soak_days_completed": 0.5,
                "soak_review_status": "insufficient_forward_paper_duration",
                "real_money_allowed": False,
                "ssl_verify": True,
                "paper_runtime_allowed": True,
                "artifact_health": {
                    "paper_soak_review": {"status": "healthy"},
                },
                "soak_review_criteria": {
                    "minimum_soak_duration_reached": {"status": "warn"},
                },
            }

            payload = _build_baseline_freeze_snapshot(
                config=config,
                readiness=readiness,
                startup_report=startup_report,
                daily_report=daily_report,
                soak_review=soak_review,
            )
            snapshot_path = _write_baseline_freeze_snapshot(config, payload)

            self.assertEqual(snapshot_path, _baseline_freeze_snapshot_path(config))
            parsed = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertFalse(parsed["real_money_allowed"])
            self.assertEqual("continue_paper_soak", parsed["manual_review"]["manual_review_outcome"])
            self.assertFalse(parsed["manual_review"]["automatic_real_money_promotion"])

    def test_manual_review_outcomes_do_not_auto_promote(self):
        soak_review = {
            "soak_review_status": "manual_promotion_review_ready",
            "real_money_allowed": False,
            "ssl_verify": True,
            "paper_runtime_allowed": True,
            "artifact_health": {
                "paper_soak_review": {"status": "healthy"},
            },
            "soak_review_criteria": {
                "criterion_a": {"status": "pass"},
            },
        }

        outcome = _manual_review_outcome_from_soak_review(soak_review)

        self.assertIn(
            outcome["manual_review_outcome"],
            [
                "continue_paper_soak",
                "paper_soak_failed",
                "eligible_for_capital_refactor_research",
                "eligible_for_tiny_live_pilot_later",
            ],
        )
        self.assertFalse(outcome["automatic_real_money_promotion"])

    def test_missing_artifacts_produce_no_go_status(self):
        soak_review = {
            "soak_review_status": "manual_review_required",
            "real_money_allowed": False,
            "ssl_verify": True,
            "paper_runtime_allowed": True,
            "artifact_health": {
                "paper_soak_review": {"status": "missing"},
            },
            "soak_review_criteria": {
                "no_stale_artifacts": {"status": "fail"},
            },
        }

        outcome = _manual_review_outcome_from_soak_review(soak_review)

        self.assertTrue(outcome["manual_review_no_go"])
        self.assertEqual("paper_soak_failed", outcome["manual_review_outcome"])

    def test_stale_runtime_warning_logic_flags_old_runtime(self):
        warnings = _build_paper_soak_warnings(
            readiness={"warnings": []},
            runtime_last_processed_timestamp="2026-06-01T00:00:00+00:00",
            heartbeat_timestamp="2026-06-01T00:00:00+00:00",
            poll_seconds=30.0,
            runtime_boundary_lag_seconds=1000.0,
        )

        self.assertTrue(any("runtime_last_processed_timestamp_stale" in item for item in warnings))
        self.assertTrue(any("engine_heartbeat_stale" in item for item in warnings))
        self.assertTrue(any("runtime_boundary_behind_expected_closed_candle" in item for item in warnings))

    def test_paper_runtime_event_jsonl_appends(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=Path(temp_dir) / "data_storage")
            first = {"startup_time": "2026-06-14T00:00:00+00:00", "restore_happened": False}
            second = {"startup_time": "2026-06-14T01:00:00+00:00", "restore_happened": True}

            event_path = _append_paper_runtime_event(config, first)
            _append_paper_runtime_event(config, second)

            self.assertEqual(event_path, _paper_runtime_events_path(config))
            lines = event_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(2, len(lines))
            self.assertFalse(json.loads(lines[0])["restore_happened"])
            self.assertTrue(json.loads(lines[1])["restore_happened"])

    def test_load_live_bootstrap_history_recovers_malformed_runtime_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(storage_base_path=temp_dir)
            folder = Path(temp_dir) / "BTCUSDT" / "1m"
            folder.mkdir(parents=True, exist_ok=True)

            final_path = folder / "BTCUSDT_1m_2018-01-01_to_2026-05-12.csv"
            final_path.write_text(
                "timestamp,open,high,low,close,volume\n"
                "2026-05-12 00:00:00,1,1,1,1,1\n"
                "2026-05-12 00:01:00,2,2,2,2,2\n",
                encoding="utf-8",
            )
            runtime_path = _runtime_state_path("BTCUSDT", "1m", config)
            runtime_path.write_text(
                "timestamp,open,high,low,close,volume\n"
                "2026-06-13 00:00:00,5,5,5,5,5\n"
                "2026-06-13 00:01:00,6,6,6,6,6,999\n"
                "2026-06-13 00:02:00,7,7,7,7,7\n",
                encoding="utf-8",
            )

            df_1m, source_path = _load_live_bootstrap_history(
                symbol="BTCUSDT",
                interval="1m",
                warmup_minutes=60 * 24 * 60,
                config=config,
            )

            self.assertEqual(source_path, runtime_path)
            self.assertTrue((folder / "BTCUSDT_1m_live_runtime.corrupt.csv").exists())
            self.assertEqual(df_1m.index[-1], pd.Timestamp("2026-06-13 00:02:00"))
            self.assertEqual(df_1m["close"].iloc[-1], 7)

    def test_momentum_ranks_prioritize_stronger_recent_symbols(self):
        dates = pd.date_range("2026-01-01", periods=5, freq="15min")
        frames = {
            "BTCUSDT": pd.DataFrame({"close": [100, 101, 102, 103, 104]}, index=dates),
            "ETHUSDT": pd.DataFrame({"close": [100, 100, 100, 100, 100]}, index=dates),
            "SOLUSDT": pd.DataFrame({"close": [100, 99, 98, 97, 96]}, index=dates),
        }

        ranks, top_symbols = _momentum_ranks(frames, lookback_bars=2)

        self.assertGreater(ranks["BTCUSDT"], ranks["ETHUSDT"])
        self.assertGreater(ranks["ETHUSDT"], ranks["SOLUSDT"])
        self.assertEqual(top_symbols[0], "BTCUSDT")

    def test_paper_soak_runbook_exists(self):
        runbook_path = Path(__file__).resolve().parents[1] / "docs" / "paper_soak_runbook.md"
        self.assertTrue(runbook_path.exists())

    def test_manual_promotion_review_runbook_exists(self):
        runbook_path = Path(__file__).resolve().parents[1] / "docs" / "manual_promotion_review.md"
        self.assertTrue(runbook_path.exists())


if __name__ == "__main__":
    unittest.main()
