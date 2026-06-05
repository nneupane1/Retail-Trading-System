import unittest

from backtest.validate_allocator_budget_sweep import (
    SWEEP_VARIANTS,
    _build_variant_verdict,
    _budget_variant_paper_overrides,
)


class _DummyBase:
    def __init__(self):
        self.data = {
            "live_sim": {
                "paper_portfolio": {
                    "strategy_sleeves": {
                        "h1_execution": {
                            "enabled": True,
                            "reserved_risk_fraction": 0.0025,
                        }
                    },
                    "allocator_v2": {
                        "cross_sleeve_coordination": {"enabled": True, "rules": {}},
                        "sleeves": {
                            "h1_execution": {
                                "absolute_max_risk_fraction": 0.0025,
                                "max_risk_fraction_multiplier": 1.10,
                            },
                            "core": {
                                "priority_multiplier": 0.78,
                                "absolute_max_risk_fraction": 0.0025,
                            },
                        },
                    },
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


class AllocatorBudgetSweepTests(unittest.TestCase):
    def test_budget_variant_overrides_raise_h1_lane_and_disable_coordination(self):
        base = _DummyBase()
        variant = SWEEP_VARIANTS[0]

        overrides = _budget_variant_paper_overrides(base, variant)

        self.assertEqual(
            variant["h1_reserved_risk_fraction"],
            overrides["strategy_sleeves"]["h1_execution"]["reserved_risk_fraction"],
        )
        self.assertEqual(
            variant["h1_absolute_max_risk_fraction"],
            overrides["allocator_v2"]["sleeves"]["h1_execution"][
                "absolute_max_risk_fraction"
            ],
        )
        self.assertFalse(
            overrides["allocator_v2"]["cross_sleeve_coordination"]["enabled"]
        )

    def test_variant_verdict_requires_positive_delta_vs_routed_h1(self):
        verdict = _build_variant_verdict(
            routed_h1={"metrics": {"trade_count": 100}},
            candidate={"metrics": {"trade_count": 98}},
            comparison={
                "delta_final_equity": 50.0,
                "delta_profit_factor": 0.02,
                "delta_median_daily_pnl": 0.01,
                "delta_max_drawdown": 0.005,
            },
        )

        self.assertTrue(verdict["is_variant_additive"])
        self.assertTrue(verdict["did_variant_preserve_flow"])


if __name__ == "__main__":
    unittest.main()
