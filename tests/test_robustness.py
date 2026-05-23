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
            self.assertTrue(Path(result["top_trades_path"]).exists())
            self.assertEqual([row["method"] for row in result["summary_rows"]], ["actual", "shuffle", "bootstrap"])


if __name__ == "__main__":
    unittest.main()
