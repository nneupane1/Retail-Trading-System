import tempfile
import unittest
from pathlib import Path

from backtest.validate_h1_portfolio import (
    _build_verdict,
    _load_h1_keep_symbols,
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


class ValidateH1PortfolioTests(unittest.TestCase):
    def test_load_h1_keep_symbols_reads_holdout_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            report_root = output_dir / "h1_execution_holdout_current"
            report_root.mkdir(parents=True, exist_ok=True)
            (report_root / "summary.json").write_text(
                '{"training_symbol_curation":{"keep_symbols":["BTCUSDT","ETHUSDT"]}}',
                encoding="utf-8",
            )
            config = _DummyConfig(str(output_dir))

            symbols = _load_h1_keep_symbols(config)

            self.assertEqual(symbols, ["BTCUSDT", "ETHUSDT"])

    def test_paper_portfolio_overrides_seed_h1_execution_sleeve(self):
        config = _DummyConfig("unused")

        overrides = _paper_portfolio_overrides(config)

        self.assertEqual(overrides["strategy_allowed_sides"]["h1_execution"], ["long", "short"])
        self.assertIn("h1_execution", overrides["strategy_sleeves"])
        self.assertIn("h1_execution", overrides["allocator_v2"]["sleeves"])

    def test_strategy_overrides_limit_h1_execution_to_keep_symbols(self):
        overrides = _strategy_overrides(["BTCUSDT", "ETHUSDT"])

        self.assertTrue(overrides["h1_execution"]["enabled"])
        self.assertEqual(overrides["h1_execution"]["allowed_symbols"], ["BTCUSDT", "ETHUSDT"])

    def test_build_verdict_requires_positive_h1_contribution(self):
        baseline = {
            "metrics": {"trade_count": 100},
            "strategy_pnl": {"h1_execution": 0.0},
        }
        candidate = {
            "metrics": {"trade_count": 98},
            "strategy_pnl": {"h1_execution": 40.0},
        }
        comparison = {
            "delta_final_equity": 90.0,
            "delta_profit_factor": 0.01,
            "delta_median_daily_pnl": -0.04,
            "delta_max_drawdown": -0.01,
        }

        verdict = _build_verdict(baseline=baseline, candidate=candidate, comparison=comparison)

        self.assertTrue(verdict["did_h1_add_positive_pnl"])
        self.assertTrue(verdict["is_h1_additive_to_portfolio"])


if __name__ == "__main__":
    unittest.main()
