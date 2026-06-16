import unittest

from structural_compounding_lab.capital import ProfitVaultState, build_convexity_profile, should_add_to_winner
from structural_compounding_lab.exit.cooldown import start_cooldown, update_cooldown


class StructuralProfitVaultTests(unittest.TestCase):
    def test_profit_lock_resets_active_capital_to_base(self):
        state = ProfitVaultState(base_capital=20000.0, active_trading_capital=23500.0, floating_profit=250.0)

        event = state.lock_profit_and_reset(reason="danger_sniffed")

        self.assertEqual(state.active_trading_capital, 20000.0)
        self.assertEqual(state.locked_profit, 3500.0)
        self.assertEqual(state.floating_profit, 0.0)
        self.assertEqual(event["cycle_id"], "cycle-1")

    def test_pyramiding_never_adds_to_loser(self):
        decision = should_add_to_winner(
            side="long",
            entry_price=100.0,
            current_price=98.0,
            active_stop_price=99.0,
            add_on_count=0,
            max_add_ons=2,
            pnl_r=-0.5,
            trigger_r=1.0,
        )
        self.assertFalse(decision)

    def test_cooldown_can_fast_resume_for_aligned_high_quality_setup(self):
        state = start_cooldown(
            bars=6,
            reason="danger_sniffed",
            minimum_bars=2,
            fast_resume_score=3.55,
            requires_danger_clear=True,
        )
        state = update_cooldown(state, danger_cleared=False, candidate_ready=False, candidate_score=0.0, aligned_setup=False)
        self.assertTrue(state.active)
        state = update_cooldown(state, danger_cleared=True, candidate_ready=True, candidate_score=3.8, aligned_setup=True)
        self.assertFalse(state.active)
        self.assertEqual(state.release_reason, "fast_resumed_for_high_quality_setup")

    def test_convexity_profile_rewards_aligned_a_setup(self):
        profile = build_convexity_profile(
            {
                "side": "long",
                "classification": "A",
                "total_score": 4.2,
                "risk_reward": 2.9,
                "htf_bias": "bullish",
                "liquidity_support": 0.72,
            }
        )
        self.assertEqual(profile["label"], "elite_convexity")
        self.assertGreater(profile["risk_multiplier"], 1.0)
        self.assertGreaterEqual(profile["add_on_budget"], 2)


if __name__ == "__main__":
    unittest.main()
