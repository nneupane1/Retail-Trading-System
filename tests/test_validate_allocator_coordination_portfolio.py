import tempfile
import unittest

from backtest.validate_allocator_coordination_portfolio import (
    _build_coordination_verdict,
    _routed_h1_paper_overrides,
)


class _DummyBase:
    def __init__(self):
        self.data = {
            "live_sim": {
                "paper_portfolio": {
                    "allocator_v2": {
                        "enabled": True,
                        "cross_sleeve_coordination": {
                            "enabled": False,
                            "rules": {
                                "h1_bearish_short": {
                                    "priority_multiplier": 1.05,
                                    "base_risk_multiplier": 1.05,
                                    "sleeve_cap_multiplier": 1.05,
                                }
                            },
                        },
                    }
                }
            }
        }

    def get(self, *keys, default=None):
        value = self.data
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value


class AllocatorCoordinationPortfolioValidationTests(unittest.TestCase):
    def test_routed_h1_overrides_toggle_coordination_flag(self):
        base = _DummyBase()

        disabled = _routed_h1_paper_overrides(base, coordination_enabled=False)
        enabled = _routed_h1_paper_overrides(base, coordination_enabled=True)

        self.assertFalse(
            disabled["allocator_v2"]["cross_sleeve_coordination"]["enabled"]
        )
        self.assertTrue(enabled["allocator_v2"]["cross_sleeve_coordination"]["enabled"])

    def test_coordination_verdict_requires_positive_portfolio_delta(self):
        verdict = _build_coordination_verdict(
            routed_h1={"metrics": {"trade_count": 100}},
            coordinated={"metrics": {"trade_count": 98}},
            comparison={
                "delta_final_equity": 125.0,
                "delta_profit_factor": 0.05,
                "delta_median_daily_pnl": 0.03,
                "delta_max_drawdown": 0.01,
            },
        )

        self.assertTrue(verdict["is_coordination_additive"])
        self.assertTrue(verdict["did_coordination_preserve_flow"])


if __name__ == "__main__":
    unittest.main()
