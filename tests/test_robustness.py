"""Tests for robustness analysis helpers."""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backtest.robustness import (
    run_monte_carlo_analysis,
    simulate_compounded_equity,
    summarize_trade_concentration,
)


class RobustnessHelpersTests(unittest.TestCase):
    def test_simulate_compounded_equity_tracks_final_equity_and_drawdown(self):
        result = simulate_compounded_equity(
            r_multiples=[1.0, -0.5, 2.0],
            initial_equity=1000.0,
            risk_per_trade=0.01,
            duration_years=1.0,
        )

        self.assertAlmostEqual(result["final_equity"], 1025.049, places=3)
        self.assertAlmostEqual(result["peak_equity"], 1025.049, places=3)
        self.assertLess(result["max_drawdown_pct"], 0.0)

    def test_simulate_compounded_equity_supports_trade_specific_risk_schedule(self):
        result = simulate_compounded_equity(
            r_multiples=[1.0, -1.0],
            initial_equity=1000.0,
            risk_per_trade=[0.01, 0.005],
            duration_years=1.0,
        )

        self.assertAlmostEqual(result["final_equity"], 1004.95, places=2)

    def test_simulate_compounded_equity_supports_realized_equity_returns(self):
        result = simulate_compounded_equity(
            r_multiples=[],
            initial_equity=1000.0,
            duration_years=1.0,
            return_fractions=[0.05, -0.01, 0.03],
        )

        self.assertAlmostEqual(result["final_equity"], 1070.685, places=3)

    def test_trade_concentration_summarizes_top_shares(self):
        trades = pd.DataFrame({"pnl": [100, 80, 20, -10]})
        summary = summarize_trade_concentration(trades)

        self.assertEqual(summary["trade_count"], 4)
        self.assertGreaterEqual(summary["top10_net_pct"], 100.0)
        self.assertGreater(summary["top10_gross_pct"], 0.0)

    def test_run_monte_carlo_analysis_writes_expected_reports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / "settings.json"
            output_dir = (root / "backtest_output").resolve()
            config_path.write_text(
                (
                    "{\n"
                    '  "account": {"initial_equity": 1000, "risk_per_trade": 0.01},\n'
                    f'  "backtest": {{"output_dir": "{output_dir.as_posix()}"}}\n'
                    "}"
                ),
                encoding="utf-8",
            )

            trades_path = root / "trades.csv"
            pd.DataFrame(
                {
                    "entry_time": ["2026-01-01", "2026-01-02", "2026-01-03"],
                    "exit_time": ["2026-01-01", "2026-01-02", "2026-01-03"],
                    "pnl": [50.0, -10.0, 30.0],
                    "pnl_R_initial": [0.5, -0.1, 0.3],
                    "initial_risk_amount": [50.0, 49.99999999999999, 51.0],
                    "equity_at_entry": [1000.0, 1050.0, 1040.0],
                    "equity_return_fraction": [0.05, -0.009523809523809525, 0.028846153846153848],
                    "side": ["long", "short", "long"],
                    "score": [8, 5, 8],
                    "pyramid_level": [0, 0, 1],
                    "exit_reason": ["trend weakness", "hard exit", "trend weakness"],
                }
            ).to_csv(trades_path, index=False)

            result = run_monte_carlo_analysis(
                trades_path=trades_path,
                config_path=config_path,
                analysis_name="unit_test",
                iterations=10,
                seed=7,
                target_equity=1100.0,
            )

            self.assertTrue(Path(result["summary_path"]).exists())
            self.assertTrue(Path(result["samples_path"]).exists())
            self.assertTrue(Path(result["concentration_path"]).exists())
            self.assertTrue(Path(result["side_contribution_path"]).exists())
            self.assertTrue(Path(result["trade_audit_path"]).exists())
            self.assertTrue(Path(result["top_trades_path"]).exists())
            self.assertEqual([row["method"] for row in result["summary_rows"]], ["actual", "shuffle", "bootstrap"])
            self.assertIn("double_equity_pct", result["summary_rows"][0])
            self.assertEqual(len(result["side_contribution"]), 2)

    def test_run_monte_carlo_analysis_supports_two_channel_portfolios(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / "settings.json"
            output_dir = (root / "backtest_output").resolve()
            config_path.write_text(
                (
                    "{\n"
                    '  "account": {"initial_equity": 1000, "risk_per_trade": 0.01},\n'
                    f'  "backtest": {{"output_dir": "{output_dir.as_posix()}"}}\n'
                    "}"
                ),
                encoding="utf-8",
            )

            trades_path = root / "portfolio_trades.csv"
            pd.DataFrame(
                {
                    "entry_time": ["2026-01-01", "2026-01-02", "2026-01-01", "2026-01-03"],
                    "exit_time": ["2026-01-01", "2026-01-02", "2026-01-01", "2026-01-03"],
                    "pnl": [60.0, -20.0, 10.0, 12.0],
                    "pnl_R_initial": [0.6, -0.2, 0.2, 0.24],
                    "initial_risk_amount": [60.0, 21.2, 10.0, 10.4],
                    "equity_at_entry": [800.0, 860.0, 200.0, 210.0],
                    "equity_return_fraction": [0.075, -0.023255813953488372, 0.05, 0.05714285714285714],
                    "side": ["long", "long", "long", "long"],
                    "entry_role": ["core", "core", "support", "support"],
                    "portfolio_channel": ["core", "core", "support", "support"],
                    "channel_initial_equity": [800.0, 800.0, 200.0, 200.0],
                    "score": [8, 8, 5, 5],
                    "pyramid_level": [1, 0, 0, 0],
                    "exit_reason": ["trend weakness", "hard exit", "trend weakness", "trend weakness"],
                }
            ).to_csv(trades_path, index=False)

            result = run_monte_carlo_analysis(
                trades_path=trades_path,
                config_path=config_path,
                analysis_name="portfolio_unit_test",
                iterations=10,
                seed=11,
                target_equity=1200.0,
            )

            self.assertTrue(result["portfolio_mode"])
            self.assertEqual(len(result["portfolio_channel_contribution"]), 2)
            self.assertTrue(Path(result["channel_contribution_path"]).exists())
            self.assertGreater(
                result["summary_rows"][0]["median_final_equity"],
                0.0,
            )


if __name__ == "__main__":
    unittest.main()
