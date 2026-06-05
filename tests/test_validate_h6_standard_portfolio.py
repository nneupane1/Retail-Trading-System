import json
import tempfile
import unittest
from pathlib import Path

from backtest.validate_h6_standard_portfolio import (
    _build_competition_report,
    _build_verdict,
    _load_h6_keep_symbols,
    _paper_portfolio_overrides,
    _strategy_overrides,
)


class _DummyConfig:
    def __init__(self, output_dir):
        self.data = {
            "backtest": {"output_dir": output_dir},
            "live_sim": {
                "paper_portfolio": {
                    "strategy_allowed_sides": {"core": ["long"]},
                    "strategy_threshold_offsets": {"core": 0.0},
                    "strategy_sleeves": {"core": {"enabled": True}},
                    "strategy_health_profiles": {},
                    "strategy_bucket_health_profiles": {},
                    "allocator_v2": {"sleeves": {"core": {"priority_multiplier": 1.0}}},
                }
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


class ValidateH6StandardPortfolioTests(unittest.TestCase):
    def test_load_h6_keep_symbols_reads_holdout_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            report_root = output_dir / "h6_standard_holdout_current"
            report_root.mkdir(parents=True, exist_ok=True)
            (report_root / "summary.json").write_text(
                json.dumps(
                    {
                        "training_symbol_curation": {
                            "keep_symbols": ["BNBUSDT", "XRPUSDT"]
                        }
                    }
                ),
                encoding="utf-8",
            )
            config = _DummyConfig(str(output_dir))

            symbols = _load_h6_keep_symbols(config)

            self.assertEqual(symbols, ["BNBUSDT", "XRPUSDT"])

    def test_paper_portfolio_overrides_seed_h6_standard_sleeve(self):
        config = _DummyConfig("unused")

        overrides = _paper_portfolio_overrides(config)

        self.assertEqual(overrides["strategy_allowed_sides"]["h6_standard"], ["long"])
        self.assertIn("h6_standard", overrides["strategy_sleeves"])
        self.assertIn("h6_standard", overrides["allocator_v2"]["sleeves"])

    def test_strategy_overrides_limit_h6_standard_to_keep_symbols(self):
        overrides = _strategy_overrides(["BNBUSDT", "XRPUSDT"])

        self.assertTrue(overrides["h6_standard"]["enabled"])
        self.assertEqual(overrides["h6_standard"]["allowed_symbols"], ["BNBUSDT", "XRPUSDT"])

    def test_build_verdict_requires_positive_h6_contribution(self):
        baseline = {
            "metrics": {"trade_count": 100},
            "strategy_pnl": {"h6_standard": 0.0},
        }
        candidate = {
            "metrics": {"trade_count": 95},
            "strategy_pnl": {"h6_standard": 50.0},
        }
        comparison = {
            "delta_final_equity": 100.0,
            "delta_profit_factor": 0.01,
            "delta_median_daily_pnl": -0.02,
            "delta_max_drawdown": -0.01,
        }

        verdict = _build_verdict(baseline=baseline, candidate=candidate, comparison=comparison)

        self.assertTrue(verdict["did_h6_standard_add_positive_pnl"])
        self.assertTrue(verdict["is_h6_standard_additive_to_portfolio"])

    def test_build_competition_report_decomposes_introduced_vs_existing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_root = Path(temp_dir)
            baseline = {
                "metrics": {"trade_count": 100, "net_pnl": 500.0},
                "strategy_breakdown": [
                    {"strategy_type": "core", "trade_count": 90, "net_pnl": 400.0},
                    {"strategy_type": "htf_12h_rotation", "trade_count": 10, "net_pnl": 100.0},
                ],
                "symbol_breakdown": [
                    {"symbol": "BTCUSDT", "trade_count": 50, "net_pnl": 250.0},
                    {"symbol": "TRXUSDT", "trade_count": 50, "net_pnl": 250.0},
                ],
            }
            candidate = {
                "metrics": {"trade_count": 95, "net_pnl": 460.0},
                "strategy_breakdown": [
                    {"strategy_type": "core", "trade_count": 82, "net_pnl": 430.0},
                    {"strategy_type": "htf_12h_rotation", "trade_count": 9, "net_pnl": 90.0},
                    {"strategy_type": "h6_standard", "trade_count": 4, "net_pnl": -60.0},
                ],
                "symbol_breakdown": [
                    {"symbol": "BTCUSDT", "trade_count": 45, "net_pnl": 210.0},
                    {"symbol": "TRXUSDT", "trade_count": 46, "net_pnl": 310.0},
                    {"symbol": "ETHUSDT", "trade_count": 4, "net_pnl": -60.0},
                ],
            }

            report = _build_competition_report(report_root, baseline, candidate, "test_overlay")

            self.assertEqual(report["introduced_strategy_types"], ["h6_standard"])
            self.assertEqual(report["introduced_trade_count"], 4)
            self.assertEqual(report["gross_displaced_existing_trade_count"], 9)
            self.assertAlmostEqual(report["introduced_net_pnl"], -60.0)
            self.assertAlmostEqual(report["existing_sleeves_delta_net_pnl"], 20.0)
            self.assertTrue((report_root / "competition_strategy_deltas_test_overlay.csv").exists())
            self.assertTrue((report_root / "competition_symbol_deltas_test_overlay.csv").exists())


if __name__ == "__main__":
    unittest.main()
