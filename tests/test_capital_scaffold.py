import json
import tempfile
import unittest
from pathlib import Path

from capital import (
    CAPITAL_REFACTOR_LAYERS,
    behavior_change_allowed,
    build_scaffold_inventory_payload,
    capital_refactor_enabled,
    layer_enabled,
    write_scaffold_inventory,
)
from capital.capital_promotion_review import build_capital_promotion_review
from capital.capital_recycling import evaluate_recycling_signal
from capital.capital_lanes import default_lane_payload
from capital.lifecycle_state_machine import LifecycleState, can_transition
from capital.opportunity_cost import OpportunityCostInput, evaluate_opportunity_cost
from capital.portfolio_heat import aggregate_portfolio_heat
from capital.regime_capital_multiplier import build_regime_multiplier
from capital.risk_bands import RiskBand, classify_risk_band
from capital.shadow_rejection_book import build_shadow_rejection_report
from capital.winner_forensics import build_top_winner_forensics
from config import AppConfig


def _base_config(root: Path) -> dict:
    return {
        "backtest": {"output_dir": str(root / "backtest" / "output")},
        "binance": {"ssl_verify": True, "ca_bundle_path": None},
        "live_sim": {
            "mode": "portfolio_paper",
            "output_dir": str(root / "live_sim" / "output"),
            "paper_portfolio": {
                "allowed_sides": ["long"],
                "strategy_allowed_sides": {"h1_execution": ["short"]},
            },
        },
        "strategy": {
            "moonshots": {"swing": {"enabled": True}},
            "h1_execution": {"enabled": True},
            "htf_12h_standard": {"enabled": True},
            "htf_12h_moonshot": {"enabled": True},
            "htf_12h_rotation": {"enabled": True},
            "h6_standard": {"enabled": False},
            "h6_moonshot": {"enabled": False},
        },
        "capital_refactor": {
            "enabled": False,
            "capital_lanes": {"enabled": False},
            "risk_bands": {"enabled": False},
            "lifecycle": {"enabled": False},
            "opportunity_cost": {"enabled": False},
            "shadow_rejection_book": {"enabled": False},
            "winner_forensics": {"enabled": False},
            "capital_recycling": {"enabled": False},
            "regime_multiplier": {"enabled": False},
            "portfolio_heat": {"enabled": False},
            "promotion_review": {"enabled": False},
        },
    }


class CapitalScaffoldTests(unittest.TestCase):
    def _config(self, root: Path) -> AppConfig:
        config_dir = root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        settings_path = config_dir / "settings.json"
        settings_path.write_text(
            json.dumps(_base_config(root), indent=2),
            encoding="utf-8",
        )
        return AppConfig.load(config_path=settings_path)

    def test_scaffold_inventory_is_written_and_parseable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = self._config(root)
            readiness = {
                "classification": "paper-only",
                "paper_runtime_allowed": True,
                "real_money_allowed": False,
                "validated_boundary": "2026-06-13T00:00:00+00:00",
                "tls": {"ssl_verify": True},
            }

            path = write_scaffold_inventory(config, readiness=readiness)

            self.assertTrue(path.exists())
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("paper-only", payload["classification"])
            self.assertTrue(payload["paper_runtime_allowed"])
            self.assertFalse(payload["real_money_allowed"])
            self.assertFalse(payload["capital_refactor_enabled"])
            self.assertFalse(payload["behavior_change_allowed"])
            self.assertEqual("2026-06-13T00:00:00+00:00", payload["validated_boundary"])
            self.assertTrue(payload["ssl_verify"])
            self.assertEqual("scaffold_only", payload["promotion_review"]["status"])
            self.assertEqual(
                "scaffold_only_no_trading_behavior_change",
                payload["warning"],
            )

    def test_capital_refactor_defaults_remain_disabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._config(Path(temp_dir))

            self.assertFalse(capital_refactor_enabled(config))
            self.assertFalse(behavior_change_allowed(config))
            for layer_name in CAPITAL_REFACTOR_LAYERS:
                self.assertFalse(layer_enabled(config, layer_name))

    def test_scaffold_payload_marks_all_layers_present_but_dormant(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._config(Path(temp_dir))

            payload = build_scaffold_inventory_payload(
                config,
                readiness={"classification": "paper-only", "tls": {"ssl_verify": True}},
            )

            self.assertEqual(len(CAPITAL_REFACTOR_LAYERS), len(payload["layer_statuses"]))
            self.assertTrue(all(row["present"] for row in payload["layer_statuses"].values()))
            self.assertTrue(all(not row["enabled"] for row in payload["layer_statuses"].values()))
            self.assertTrue(all(not row["behavior_change_allowed"] for row in payload["layer_statuses"].values()))
            self.assertEqual(4, len(default_lane_payload()))

    def test_capital_promotion_review_cannot_promote(self):
        review = build_capital_promotion_review()

        self.assertEqual("scaffold_only", review["status"])
        self.assertFalse(review["behavior_change_allowed"])
        self.assertFalse(review["real_money_allowed"])

    def test_scaffold_helpers_are_inert_and_parseable(self):
        risk_band = classify_risk_band(equity=92_000, peak_equity=100_000, in_recovery=True)
        transition_allowed = can_transition(LifecycleState.CANDIDATE, LifecycleState.PROBE)
        opportunity = evaluate_opportunity_cost(
            OpportunityCostInput(
                current_position_score=0.80,
                candidate_score=1.25,
                capital_locked_duration_hours=16.0,
                unrealized_r=-0.2,
                competing_signal_priority=1.10,
            )
        )
        rejection_report = build_shadow_rejection_report()
        winner_report = build_top_winner_forensics()
        recycling_signal = evaluate_recycling_signal(
            hours_held=30.0,
            unrealized_r=-0.2,
            replacement_score=1.4,
        )
        regime_multiplier = build_regime_multiplier(
            trend_regime="aligned",
            volatility_regime="stable",
            correlation_regime="low",
            risk_on_risk_off_regime="risk_on",
        )
        heat = aggregate_portfolio_heat(
            positions=[
                {"symbol": "BTCUSDT", "side": "long", "strategy_type": "core", "risk_fraction": 0.01},
                {"symbol": "ETHUSDT", "side": "short", "strategy_type": "h1_execution", "risk_fraction": 0.0075},
            ]
        )

        self.assertEqual(RiskBand.RECOVERY, risk_band.band)
        self.assertTrue(transition_allowed)
        self.assertGreater(opportunity.opportunity_cost_score, 0.0)
        self.assertEqual([], rejection_report["records"])
        self.assertEqual([], winner_report["records"])
        self.assertTrue(recycling_signal.recycling_candidate)
        self.assertEqual("aligned", regime_multiplier.trend_regime)
        self.assertAlmostEqual(1.07, regime_multiplier.regime_multiplier)
        self.assertAlmostEqual(0.0175, heat.total_open_risk)
        self.assertAlmostEqual(0.01, heat.correlated_long_exposure)
        self.assertAlmostEqual(0.0075, heat.correlated_short_exposure)


if __name__ == "__main__":
    unittest.main()
