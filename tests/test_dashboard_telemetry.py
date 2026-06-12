import json
import tempfile
import unittest
from pathlib import Path

from common.dashboard_telemetry import build_trade_markers, list_live_runs, load_live_dashboard_snapshot, load_symbol_candles


class DummyConfig:
    def __init__(self, root_dir):
        self.root_dir = Path(root_dir)
        self.data = {
            "live_sim": {
                "output_dir": str(self.root_dir / "live_output"),
            },
            "storage": {
                "base_path": str(self.root_dir / "data_storage"),
            },
            "binance": {
                "default_interval": "1m",
            },
            "history": {
                "start_date": "2018-01-01",
                "end_date": "2026-05-12",
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


class DashboardTelemetryTests(unittest.TestCase):
    def test_load_live_dashboard_snapshot_reads_status_and_csvs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "portfolio_status.json").write_text(
                json.dumps({"equity": 12345, "runtime_policy_states": {"h1_execution": {"label": "boost_active"}}}),
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

            payload = load_live_dashboard_snapshot(root)

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
