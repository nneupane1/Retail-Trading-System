import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

import backtest.portfolio_runner as portfolio_runner
from backtest.runner import run_backtest


class DummyConfig:
    def __init__(self, storage_base_path, output_dir):
        self.data = {
            "app": {
                "default_symbol": "BTCUSDT",
            },
            "account": {
                "initial_equity": 1000.0,
            },
            "backtest": {
                "mode": "portfolio_replay",
                "output_dir": output_dir,
                "opportunity_log_enabled": False,
                "portfolio_replay": {
                    "symbols": ["BTCUSDT", "ETHUSDT"],
                    "signal_log_filename": "signals.csv",
                    "minimum_execution_bars": 0,
                    "close_open_positions_at_end": True,
                },
            },
            "binance": {
                "default_interval": "1m",
            },
            "storage": {
                "base_path": storage_base_path,
            },
            "history": {
                "start_date": "2026-01-01",
                "end_date": "2026-01-02",
            },
            "universe": {
                "active_set": "current_9",
                "symbol_sets": {
                    "current_9": ["BTCUSDT", "ETHUSDT"],
                    "expanded_liquid_28": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
                },
            },
            "position": {
                "min_stop_distance_ratio": 0.0001,
                "min_stop_distance_absolute": 0.0,
                "max_position_size_units": None,
                "max_notional_equity_multiple": None,
            },
            "features": {
                "ema_periods": {"fast": 2, "slow": 3},
                "structure": {"high_period": 2, "low_period": 2},
                "compression": {
                    "fast_range_period": 2,
                    "slow_range_period": 3,
                    "ratio": 0.8,
                },
                "pressure": {
                    "mean_reversion_vwap_distance_threshold": 0.01,
                    "mean_reversion_wick_threshold": 1.2,
                },
                "candle_metrics": {"average_body_period": 2},
                "indicators": {
                    "atr_period": 2,
                    "macd_fast_period": 2,
                    "macd_slow_period": 3,
                    "macd_signal_period": 2,
                    "bollinger_period": 2,
                    "bollinger_std_dev": 2.0,
                },
            },
            "strategy": {
                "edge_selection": {
                    "enabled": False,
                    "strong_body_threshold": 1.2,
                    "vwap_far_threshold": 0.01,
                    "impulse_body_threshold": 2.0,
                    "impulse_close_threshold": 0.75,
                    "pressure_body_threshold": 1.2,
                    "pullback_body_threshold": 1.0,
                },
                "scoring": {
                    "body_strength_min": 1.2,
                    "close_position_min": 0.6,
                    "close_position_max": 0.4,
                },
                "bias": {
                    "ema_column": "ema3",
                    "slope_lookback": 1,
                    "slope_threshold": 0.0,
                },
                "sniffing": {
                    "body_strength_min": 0.8,
                    "close_position_min": 0.4,
                    "close_position_max": 0.6,
                    "upper_wick_max": 1.5,
                    "lower_wick_max": 1.5,
                    "min_confirmations": 1,
                    "relax_after_r": 1.0,
                    "relaxed_min_confirmations": 0,
                    "require_short_vwap_alignment": True,
                    "support_alpha": {},
                    "by_side": {},
                    "trailing": {
                        "strong_body_min": 1.0,
                        "clean_wick_max": 1.0,
                        "min_vwap_distance": 0.0,
                        "min_ema_gap": 0.0,
                        "vwap_decay_threshold": 0.0015,
                        "ema_gap_decay_threshold": 0.0010,
                        "macd_decay_threshold": 0.0,
                        "body_decay_max": 0.8,
                        "wick_decay_min": 1.5,
                        "decay_close_position_max": 0.45,
                        "strong_close_position_min": 0.65,
                        "init_max_r": 0.5,
                        "confirmation_max_r": 1.5,
                        "expansion_min_momentum_signals": 4,
                        "decay_signal_threshold": 2,
                        "force_exit_decay_signal_threshold": 4,
                        "init_atr_buffer": 1.2,
                        "confirmation_atr_buffer": 0.9,
                        "expansion_atr_buffer": 1.8,
                        "decay_atr_buffer": 0.35,
                        "exit_atr_buffer": 0.15,
                        "expansion_anchor": "slow_ema",
                        "decay_anchor": "fast_ema",
                        "confirmation_anchor": "fast_ema",
                        "by_side": {},
                    },
                },
            },
            "timeframes": {
                "base": {"rule": "1min"},
                "execution": {"rule": "15min"},
                "direction": {"rule": "1h"},
                "resample": {
                    "closed": "left",
                    "label": "right",
                    "drop_incomplete": True,
                },
            },
            "live_sim": {
                "universe": {
                    "symbols": ["BTCUSDT", "ETHUSDT"],
                    "momentum_lookback_bars": 1,
                },
                "opportunity_scoring": {
                    "weights": {
                        "body_strength": 0.35,
                        "close_position": 0.25,
                        "vwap_score": 0.25,
                        "momentum": 0.15,
                    }
                },
                "paper_portfolio": {
                    "allowed_sides": ["long"],
                    "allowed_edge_types": ["impulse_breakout", "breakout_pullback", "pressure_breakout"],
                    "min_trades_per_day": 2,
                    "target_trades_per_day": 2,
                    "max_trades_per_day": 4,
                    "base_threshold": 0.60,
                    "min_threshold": 0.50,
                    "max_threshold": 0.90,
                    "pacing_relax_step": 0.05,
                    "pacing_tighten_step": 0.03,
                    "threshold_smoothing": 0.20,
                    "min_profitable_bucket_count": 2,
                    "min_risk_per_trade": 0.0025,
                    "max_risk_per_trade": 0.0060,
                    "max_total_risk_fraction": 0.04,
                    "max_trades_per_asset": 2,
                    "max_same_direction_positions": 6,
                    "trailing_activation_r": 1.2,
                    "breakeven_trigger_r": 1.0,
                    "slow_grind_max_bars": 8,
                    "slow_grind_open_r_max": 1.0,
                    "weight_update_min_trades": 2,
                },
            },
        }

    def get(self, *keys, default=None):
        value = self.data
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value

    def require(self, *keys):
        value = self.data
        for key in keys:
            value = value[key]
        return value


def _write_symbol_history(folder, symbol):
    index = pd.date_range("2026-01-01 00:00:00", periods=360, freq="1min")
    base = pd.Series(range(len(index)), index=index, dtype=float)
    close = 100.0 + (base * 0.05)
    frame = pd.DataFrame(
        {
            "timestamp": index,
            "open": close - 0.05,
            "high": close + 0.10,
            "low": close - 0.10,
            "close": close,
            "volume": 1000.0,
        }
    )
    target = folder / f"{symbol}_1m_2026-01-01_to_2026-01-02.csv"
    frame.to_csv(target, index=False)


class PortfolioBacktestRunnerTests(unittest.TestCase):
    def test_discover_portfolio_symbols_can_use_named_universe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_dir = Path(temp_dir) / "data_storage"
            output_dir = Path(temp_dir) / "backtest_output"
            config = DummyConfig(
                storage_base_path=str(storage_dir),
                output_dir=str(output_dir),
            )
            config.data["backtest"]["portfolio_replay"]["symbols"] = []
            config.data["live_sim"]["universe"]["symbols"] = []
            config.data["backtest"]["portfolio_replay"]["universe_name"] = "expanded_liquid_28"

            symbols = portfolio_runner._discover_portfolio_symbols(config)

            self.assertEqual(symbols, ["BTCUSDT", "ETHUSDT", "SOLUSDT"])

    def test_resolve_history_file_accepts_later_starting_timestamped_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            candidate = folder / "SUIUSDT_1m_2023-05-01T00.00.00_to_2026-01-03T00.00.00.csv"
            candidate.write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")

            resolved = portfolio_runner._resolve_history_file(
                folder,
                symbol="SUIUSDT",
                interval="1m",
                start_date="2026-01-01",
                end_date="2026-01-02",
            )

            self.assertEqual(resolved, candidate)

    def test_build_checkpoint_store_uses_compact_name_for_long_output_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = (
                Path(temp_dir)
                / "expanded_universe_allocator_validation_20260604"
                / "scenario_current_9_symbol_calibrated_allocator"
            )
            config = DummyConfig(
                storage_base_path=str(Path(temp_dir) / "data_storage"),
                output_dir=str(output_dir),
            )

            checkpoint_store = portfolio_runner._build_checkpoint_store(
                config,
                output_dir,
                ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            )

            self.assertLess(len(str(checkpoint_store.path)), 240)
            self.assertTrue(
                checkpoint_store.path.name.startswith("portfolio_replay_3symbols_")
                or checkpoint_store.path.name.startswith("pr_3symbols_")
            )

    def test_portfolio_replay_ignores_broken_artifact_resume_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_dir = Path(temp_dir) / "data_storage"
            output_dir = Path(temp_dir) / "backtest_output"
            for symbol in ("BTCUSDT", "ETHUSDT"):
                symbol_dir = storage_dir / symbol / "1m"
                symbol_dir.mkdir(parents=True, exist_ok=True)
                _write_symbol_history(symbol_dir, symbol)

            config = DummyConfig(
                storage_base_path=str(storage_dir),
                output_dir=str(output_dir),
            )

            with mock.patch.object(
                portfolio_runner,
                "_build_artifact_resume_payload",
                side_effect=ValueError("bad artifacts"),
            ):
                result = run_backtest(config=config)

            self.assertTrue(getattr(result, "backtest_completed", False))
            self.assertTrue((output_dir / "portfolio_status.json").exists())

    def test_run_backtest_dispatches_to_portfolio_replay_and_writes_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_dir = Path(temp_dir) / "data_storage"
            output_dir = Path(temp_dir) / "backtest_output"
            for symbol in ("BTCUSDT", "ETHUSDT"):
                symbol_dir = storage_dir / symbol / "1m"
                symbol_dir.mkdir(parents=True, exist_ok=True)
                _write_symbol_history(symbol_dir, symbol)

            config = DummyConfig(
                storage_base_path=str(storage_dir),
                output_dir=str(output_dir),
            )

            result = run_backtest(config=config)

            self.assertTrue(getattr(result, "backtest_completed", False))
            self.assertTrue((output_dir / "trades.csv").exists())
            self.assertTrue((output_dir / "equity.csv").exists())
            self.assertTrue((output_dir / "signals.csv").exists())
            self.assertTrue((output_dir / "score_bucket_summary.csv").exists())
            self.assertTrue((output_dir / "daily_summary.csv").exists())
            self.assertTrue((output_dir / "portfolio_status.json").exists())

            with (output_dir / "portfolio_status.json").open(encoding="utf-8") as file_handle:
                payload = json.load(file_handle)
            self.assertIn("equity", payload)

    def test_portfolio_replay_saves_checkpoint_on_interrupt_and_resumes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_dir = Path(temp_dir) / "data_storage"
            output_dir = Path(temp_dir) / "backtest_output"
            for symbol in ("BTCUSDT", "ETHUSDT"):
                symbol_dir = storage_dir / symbol / "1m"
                symbol_dir.mkdir(parents=True, exist_ok=True)
                _write_symbol_history(symbol_dir, symbol)

            config = DummyConfig(
                storage_base_path=str(storage_dir),
                output_dir=str(output_dir),
            )

            original_flush_state = portfolio_runner.LivePaperPortfolio.flush_state
            interrupted = {"done": False}

            def interrupt_once(self):
                if not interrupted["done"]:
                    interrupted["done"] = True
                    raise KeyboardInterrupt()
                return original_flush_state(self)

            with mock.patch.object(
                portfolio_runner.LivePaperPortfolio,
                "flush_state",
                new=interrupt_once,
            ):
                first_result = run_backtest(config=config)

            checkpoint_files = list((output_dir / "_checkpoints").glob("*.checkpoint.json"))
            self.assertFalse(getattr(first_result, "backtest_completed", False))
            self.assertEqual(len(checkpoint_files), 1)

            resumed_result = run_backtest(config=config)

            self.assertTrue(getattr(resumed_result, "backtest_completed", False))
            self.assertFalse(checkpoint_files[0].exists())
            self.assertTrue((output_dir / "portfolio_status.json").exists())


if __name__ == "__main__":
    unittest.main()
