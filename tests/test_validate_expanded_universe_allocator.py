import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd

from backtest.validate_expanded_universe_allocator import (
    _build_or_resume_quality_report,
    _build_symbol_curation_report,
    _classify_curated_symbol,
    _daily_quote_volume_stats,
    _load_quality_progress,
    _resolve_candidate_symbols,
    _seed_scenario_progress,
    _scenario_artifacts_require_symbol_reset,
    _scenario_requires_symbol_reset,
    _should_skip_expanded_scenario,
    _terminal_gap_minutes,
    _validate_symbol_quality,
)


class ValidateExpandedUniverseAllocatorTests(unittest.TestCase):
    def test_validate_symbol_quality_records_feature_generation_error_stage(self):
        class _ConfigStub:
            def require(self, *keys):
                mapping = {
                    ("binance", "default_interval"): "1m",
                    ("history", "start_date"): "2026-05-20",
                    ("history", "end_date"): "2026-05-22",
                }
                return mapping[keys]

            def get(self, *keys, default=None):
                return default

        index = pd.date_range("2026-05-20 00:00:00", periods=1440 * 3, freq="1min")
        clean_1m = pd.DataFrame(
            {
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
                "volume": 100.0,
            },
            index=index,
        )
        raw_frame = clean_1m.reset_index().rename(columns={"index": "timestamp"})
        thresholds = {
            "max_missing_1m_ratio": 1.0,
            "max_missing_15m_ratio": 1.0,
            "max_duplicate_1m_ratio": 1.0,
            "max_ohlcv_nan_ratio": 1.0,
            "min_recent_execution_rows": 0,
            "min_recent_12h_rows": 0,
            "min_recent_1d_rows": 0,
            "min_recent_median_daily_quote_volume": 0.0,
            "min_recent_min_daily_quote_volume": 0.0,
            "max_recent_spread_proxy": 1.0,
            "min_daily_bar_coverage_ratio_for_liquidity_stats": 0.95,
            "max_recent_terminal_gap_minutes": 999999.0,
        }

        with patch(
            "backtest.validate_expanded_universe_allocator._load_full_history",
            return_value=(clean_1m, "fake.csv"),
        ), patch(
            "backtest.validate_expanded_universe_allocator._read_raw_history_csv",
            return_value=raw_frame,
        ), patch(
            "backtest.validate_expanded_universe_allocator._build_strategy_timeframes",
            side_effect=OSError(22, "Invalid argument"),
        ):
            row = _validate_symbol_quality(
                "TESTUSDT",
                base_config=_ConfigStub(),
                recent_start="2026-05-20",
                recent_end="2026-05-22",
                thresholds=thresholds,
            )

        self.assertEqual("feature_generation_failed", row["reject_reason"])
        self.assertEqual("timeframe_build", row["error_stage"])
        self.assertIn("Invalid argument", row["error"])
        self.assertIn("OSError", row["traceback"])

    def test_resolve_candidate_symbols_uses_binance_discovery_when_enabled(self):
        class _ConfigStub:
            def get(self, *keys, default=None):
                if keys == ("universe", "discovery", "enabled"):
                    return True
                return default

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "backtest.validate_expanded_universe_allocator.discover_binance_candidate_universe",
            return_value={"candidate_symbols": ["BTCUSDT", "DOTUSDT"], "summary": {"candidate_symbol_count": 2}},
        ), patch(
            "backtest.validate_expanded_universe_allocator.write_discovery_reports",
            return_value={"artifacts": {}},
        ):
            symbols, source = _resolve_candidate_symbols(_ConfigStub(), Path(tmpdir))

        self.assertEqual(["BTCUSDT", "DOTUSDT"], symbols)
        self.assertEqual("binance_discovery", source["source"])

    def test_classify_curated_symbol_marks_keep_when_symbol_is_consistently_positive(self):
        status = _classify_curated_symbol(
            {
                "trade_count": 90,
                "net_pnl": 250.0,
                "avg_R": 0.04,
                "profit_factor": 1.3,
            },
            {
                "min_keep_trade_count": 75,
                "min_keep_net_pnl": 0.0,
                "min_keep_avg_R": 0.0,
                "min_keep_profit_factor": 1.0,
                "min_review_trade_count": 40,
            },
        )
        self.assertEqual("keep", status)

    def test_symbol_curation_report_builds_curated_symbol_set_from_expanded_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = _build_symbol_curation_report(
                base_config=object(),
                report_root=Path(tmpdir),
                baseline_symbols=["BTCUSDT", "ETHUSDT"],
                expanded_snapshot={
                    "metrics": {"net_pnl": 1000.0},
                    "symbol_breakdown": [
                        {
                            "symbol": "BTCUSDT",
                            "trade_count": 100,
                            "net_pnl": 10.0,
                            "avg_R": 0.01,
                            "median_R": 0.0,
                            "max_R": 1.0,
                            "win_rate": 0.5,
                            "profit_factor": 1.1,
                            "loss_contribution_proxy": -10.0,
                        },
                        {
                            "symbol": "ADAUSDT",
                            "trade_count": 80,
                            "net_pnl": 120.0,
                            "avg_R": 0.03,
                            "median_R": 0.0,
                            "max_R": 2.0,
                            "win_rate": 0.5,
                            "profit_factor": 1.2,
                            "loss_contribution_proxy": -50.0,
                        },
                        {
                            "symbol": "DOGEUSDT",
                            "trade_count": 90,
                            "net_pnl": -20.0,
                            "avg_R": -0.01,
                            "median_R": -0.01,
                            "max_R": 1.0,
                            "win_rate": 0.4,
                            "profit_factor": 0.9,
                            "loss_contribution_proxy": -60.0,
                        },
                    ],
                },
                accepted_symbols=["BTCUSDT", "ETHUSDT", "ADAUSDT", "DOGEUSDT"],
            )

            self.assertEqual(["ADAUSDT"], payload["keep_symbols"])
            self.assertEqual(["DOGEUSDT"], payload["drop_symbols"])
            self.assertEqual(["BTCUSDT", "ETHUSDT", "ADAUSDT"], payload["curated_symbols"])

    def test_daily_quote_volume_stats_ignores_incomplete_terminal_day(self):
        index = pd.date_range("2026-05-20 00:00:00", periods=1440 * 2 + 1, freq="1min")
        frame = pd.DataFrame(
            {
                "close": 1.0,
                "volume": 100.0,
            },
            index=index,
        )
        min_qv, median_qv, full_day_count = _daily_quote_volume_stats(frame, min_bar_coverage_ratio=0.95)

        self.assertEqual(2, full_day_count)
        self.assertEqual(144000.0, min_qv)
        self.assertEqual(144000.0, median_qv)

    def test_terminal_gap_minutes_is_zero_for_complete_series(self):
        self.assertEqual(
            0.0,
            _terminal_gap_minutes(
                pd.Timestamp("2026-05-22 23:59:00"),
                pd.Timestamp("2026-05-22 23:59:00"),
            ),
        )

    def test_terminal_gap_minutes_reflects_partial_terminal_day(self):
        self.assertEqual(
            1439.0,
            _terminal_gap_minutes(
                pd.Timestamp("2026-05-22 00:00:00"),
                pd.Timestamp("2026-05-22 23:59:00"),
            ),
        )

    def test_quality_report_refreshes_completed_cached_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report_root = Path(tmpdir)
            base_config = object()

            report_calls = []

            def fake_validate(symbol, **_kwargs):
                report_calls.append(symbol)
                return {
                    "symbol": symbol,
                    "accepted": True,
                    "reject_reason": "",
                    "reasons": [],
                }

            cached_progress = {
                "symbols": {
                    "ADAUSDT": {
                        "symbol": "ADAUSDT",
                        "accepted": False,
                        "reject_reason": "missing_local_history",
                        "reasons": ["missing_local_history"],
                        "complete": True,
                    }
                }
            }

            with patch(
                "backtest.validate_expanded_universe_allocator._quality_thresholds",
                return_value={},
            ), patch(
                "backtest.validate_expanded_universe_allocator._curation_thresholds",
                return_value={
                    "min_keep_trade_count": 75,
                    "min_keep_net_pnl": 0.0,
                    "min_keep_avg_R": 0.0,
                    "min_keep_profit_factor": 1.0,
                    "min_review_trade_count": 40,
                },
            ), patch(
                "backtest.validate_expanded_universe_allocator._validate_symbol_quality",
                side_effect=fake_validate,
            ), patch(
                "backtest.validate_expanded_universe_allocator._write_universe_quality_reports",
                return_value={
                    "accepted_symbols": ["ADAUSDT"],
                    "rejected_symbols": [],
                    "accepted_symbol_count": 1,
                    "rejected_symbol_count": 0,
                },
            ):
                # Seed stale cached progress first.
                from backtest.validate_expanded_universe_allocator import _save_quality_progress

                _save_quality_progress(report_root, cached_progress)

                result = _build_or_resume_quality_report(
                    base_config=base_config,
                    report_root=report_root,
                    candidate_symbols=["ADAUSDT"],
                    recent_start="2025-01-01",
                    recent_end="2026-05-22",
                )

            self.assertEqual(["ADAUSDT"], report_calls)
            self.assertEqual(["ADAUSDT"], result["accepted_symbols"])
            refreshed = _load_quality_progress(report_root)
            self.assertTrue(refreshed["symbols"]["ADAUSDT"]["accepted"])
            self.assertEqual("", refreshed["symbols"]["ADAUSDT"]["reject_reason"])

    def test_skip_expanded_scenario_when_no_net_new_symbols(self):
        skip, reason = _should_skip_expanded_scenario(
            ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            ["ETHUSDT", "BTCUSDT"],
        )
        self.assertTrue(skip)
        self.assertEqual("no_net_universe_expansion_after_quality_validation", reason)

    def test_do_not_skip_expanded_scenario_when_new_symbol_is_admitted(self):
        skip, reason = _should_skip_expanded_scenario(
            ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT"],
        )
        self.assertFalse(skip)
        self.assertIsNone(reason)

    def test_scenario_reset_triggers_when_symbol_set_changes(self):
        progress = {
            "scenario_expanded_universe_calibrated_allocator": {
                "symbols_used": ["ETHUSDT", "BTCUSDT", "SOLUSDT"]
            }
        }
        self.assertTrue(
            _scenario_requires_symbol_reset(
                progress,
                "scenario_expanded_universe_calibrated_allocator",
                ["BTCUSDT", "ETHUSDT", "ADAUSDT"],
            )
        )

    def test_scenario_reset_reads_legacy_short_progress_key(self):
        progress = {
            "expanded_universe_calibrated_allocator": {
                "symbols_used": ["ETHUSDT", "BTCUSDT", "SOLUSDT"]
            }
        }
        self.assertTrue(
            _scenario_requires_symbol_reset(
                progress,
                "scenario_expanded_universe_calibrated_allocator",
                ["BTCUSDT", "ETHUSDT", "ADAUSDT"],
            )
        )

    def test_scenario_reset_ignores_symbol_order(self):
        progress = {
            "scenario_expanded_universe_calibrated_allocator": {
                "symbols_used": ["ETHUSDT", "BTCUSDT", "SOLUSDT"]
            }
        }
        self.assertFalse(
            _scenario_requires_symbol_reset(
                progress,
                "scenario_expanded_universe_calibrated_allocator",
                ["SOLUSDT", "ETHUSDT", "BTCUSDT"],
            )
        )

    def test_seed_scenario_progress_initializes_registry_entry(self):
        progress = {}
        entry = _seed_scenario_progress(
            progress,
            "scenario_expanded_universe_calibrated_allocator",
            ["btcusdt", "EthUsdt"],
            status="in_progress",
            reset_output=True,
        )

        self.assertEqual(["BTCUSDT", "ETHUSDT"], entry["symbols_used"])
        self.assertEqual("in_progress", entry["status"])
        self.assertTrue(entry["reset_output_requested"])
        self.assertFalse(entry["completed"])

    def test_artifact_symbol_reset_triggers_on_unexpected_symbol(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scenario_dir = Path(tmpdir) / "scenario_expanded_universe_calibrated_allocator"
            scenario_dir.mkdir(parents=True)
            pd.DataFrame(
                [
                    {"symbol": "BTCUSDT"},
                    {"symbol": "ADAUSDT"},
                ]
            ).to_csv(scenario_dir / "trades.csv", index=False)

            self.assertTrue(
                _scenario_artifacts_require_symbol_reset(
                    Path(tmpdir),
                    "scenario_expanded_universe_calibrated_allocator",
                    ["BTCUSDT", "ETHUSDT"],
                )
            )

    def test_artifact_symbol_reset_ignores_expected_symbols(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scenario_dir = Path(tmpdir) / "scenario_expanded_universe_calibrated_allocator"
            scenario_dir.mkdir(parents=True)
            pd.DataFrame(
                [
                    {"symbol": "BTCUSDT"},
                    {"symbol": "ETHUSDT"},
                ]
            ).to_csv(scenario_dir / "trades.csv", index=False)

            self.assertFalse(
                _scenario_artifacts_require_symbol_reset(
                    Path(tmpdir),
                    "scenario_expanded_universe_calibrated_allocator",
                    ["BTCUSDT", "ETHUSDT"],
                )
            )


if __name__ == "__main__":
    unittest.main()
