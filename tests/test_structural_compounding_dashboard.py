import json
import tempfile
import unittest
from pathlib import Path

from common.dashboard_telemetry import load_structural_lab_snapshot


class StructuralCompoundingDashboardTests(unittest.TestCase):
    def test_snapshot_returns_honest_empty_state_without_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "structural_compounding_lab" / "config").mkdir(parents=True, exist_ok=True)
            (root / "structural_compounding_lab" / "config" / "structural_compounding_settings.json").write_text(
                json.dumps({"base_capital": 20000, "visual_timeframes": ["1h", "12h"]}),
                encoding="utf-8",
            )
            (root / "structural_compounding_lab" / "config" / "symbols.json").write_text(
                json.dumps({"symbols": ["BTCUSDT"]}),
                encoding="utf-8",
            )

            snapshot = load_structural_lab_snapshot(root_dir=root)

            self.assertFalse(snapshot["lab"]["has_run"])
            self.assertEqual(snapshot["lab"]["empty_state"], "No structural backtest run found yet.")
            self.assertIn("No structural backtest run found yet.", snapshot["warnings"])
            self.assertIn("BTCUSDT", snapshot["available_symbols"])
            self.assertTrue(snapshot["trade_frequency_pnl"]["metadata"]["read_only"])
            self.assertEqual(0, snapshot["trade_frequency_pnl"]["metadata"]["row_count"])
            self.assertTrue(snapshot["daily_structural_opportunity"]["metadata"]["read_only"])
            self.assertEqual([], snapshot["daily_structural_opportunity"]["top_opportunity_by_day"])

    def test_snapshot_reads_structural_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_root = root / "structural_compounding_lab" / "config"
            output_root = root / "structural_compounding_lab" / "output"
            config_root.mkdir(parents=True, exist_ok=True)
            output_root.mkdir(parents=True, exist_ok=True)

            (config_root / "structural_compounding_settings.json").write_text(
                json.dumps({"base_capital": 20000, "visual_timeframes": ["1h", "4h", "12h"]}),
                encoding="utf-8",
            )
            (config_root / "symbols.json").write_text(
                json.dumps({"symbols": ["BTCUSDT", "ETHUSDT"]}),
                encoding="utf-8",
            )
            (output_root / "summary.json").write_text(
                json.dumps(
                    {
                        "current_equity": 24500,
                        "locked_profit": 3000,
                        "active_trading_capital": 20000,
                        "cooldown_active": False,
                        "current_compounding_cycle": "cycle-3",
                        "metrics": {
                            "total_return_pct": 0.225,
                            "max_drawdown_pct": 0.08,
                            "win_rate": 0.56,
                            "profit_factor": 1.34,
                            "r_multiple_summary": "1R and 2R winners dominate while moonshots remain rare."
                        }
                    }
                ),
                encoding="utf-8",
            )
            (output_root / "profit_vault.json").write_text(
                json.dumps(
                    {
                        "base_capital": 20000,
                        "active_trading_capital": 20000,
                        "locked_profit": 3000,
                        "floating_profit": 1500,
                        "current_compounding_cycle_id": "cycle-3"
                    }
                ),
                encoding="utf-8",
            )
            (output_root / "trades.csv").write_text(
                "symbol,side,pnl,entry_reason,exit_reason,entry_time,exit_time,r_multiple\nBTCUSDT,long,250,sweep reclaim,trail exit,2026-01-02T08:00:00+00:00,2026-01-02T10:00:00+00:00,1.4\n",
                encoding="utf-8",
            )
            diagnostics_root = output_root / "diagnostics"
            reports_root = output_root / "reports"
            diagnostics_root.mkdir(parents=True, exist_ok=True)
            reports_root.mkdir(parents=True, exist_ok=True)
            (diagnostics_root / "pullback_quality_report.json").write_text(
                json.dumps({"count": 1, "average_improved_R_delta": 1.2}),
                encoding="utf-8",
            )
            daily_root = output_root / "daily_opportunity_definition_refinement_001"
            (daily_root / "diagnostics").mkdir(parents=True, exist_ok=True)
            (daily_root / "reports").mkdir(parents=True, exist_ok=True)
            (daily_root / "status.json").write_text(
                json.dumps({"state": "complete", "classification": "continue_research", "real_money_allowed": False}),
                encoding="utf-8",
            )
            (daily_root / "definition_refinement_summary.json").write_text(
                json.dumps(
                    {
                        "classification": "continue_research",
                        "days_analyzed": 12,
                        "valid_opportunity_days": 5,
                        "strong_structural_hill_days": 2,
                        "no_opportunity_days": 4,
                        "too_tight_day_count": 2,
                        "missed_high_R_opportunity_count": 1,
                        "high_R_probe_day_count": 2,
                        "noise_chasing_avoided_count": 3,
                        "full_size_count": 1,
                        "reduced_size_count": 1,
                        "probe_count": 3,
                        "reject_invalid_count": 4,
                        "actual_trade_frequency": {"actual_trade_count": 3, "actual_trade_days": 2},
                        "resolved_at_utc": "2026-06-16T18:00:00+00:00",
                        "source_files": ["daily_opportunities.csv"],
                    }
                ),
                encoding="utf-8",
            )
            (daily_root / "diagnostics" / "top_opportunity_by_day.csv").write_text(
                "date,symbol,side,opportunity_label,opportunity_score,best_archetype,best_personality,participation_mode,expected_R_potential,room_to_target_score,danger_score,explanation\n"
                "2026-06-01,BTCUSDT,long,STRONG_STRUCTURAL_HILL,77.2,LIQUIDITY_SWEEP_RECLAIM,PULLBACK_CONTINUATION,FULL_SIZE_CANDIDATE,4.5,0.92,0.21,clean structural day\n",
                encoding="utf-8",
            )
            (daily_root / "diagnostics" / "participation_routed_daily_candidates.csv").write_text(
                "date,symbol,side,opportunity_label,participation_mode\n2026-06-01,BTCUSDT,long,STRONG_STRUCTURAL_HILL,FULL_SIZE_CANDIDATE\n",
                encoding="utf-8",
            )
            (daily_root / "diagnostics" / "participation_mode_distribution.json").write_text(
                json.dumps({"counts": {"FULL_SIZE_CANDIDATE": 1, "REJECT_INVALID": 4}}),
                encoding="utf-8",
            )
            (daily_root / "diagnostics" / "sr_zone_opportunity_report.json").write_text(
                json.dumps({"breakout_retest_hold_days": 2, "average_zone_quality_score": 0.7}),
                encoding="utf-8",
            )
            (daily_root / "diagnostics" / "breakout_retest_report.json").write_text(
                json.dumps({"breakout_supportive_days": 3}),
                encoding="utf-8",
            )
            (daily_root / "diagnostics" / "missed_daily_opportunity_report.json").write_text(
                json.dumps({"missed_high_r_opportunities": []}),
                encoding="utf-8",
            )
            (daily_root / "diagnostics" / "too_tight_inactivity_report.json").write_text(
                json.dumps({"too_tight_day_count": 2}),
                encoding="utf-8",
            )
            (daily_root / "diagnostics" / "noise_chasing_guard_report.json").write_text(
                json.dumps({"noise_chasing_avoided_count": 3, "tiny_wiggle_flag_count": 5}),
                encoding="utf-8",
            )
            (daily_root / "diagnostics" / "high_r_opportunity_report.json").write_text(
                json.dumps({"high_r_day_count": 2}),
                encoding="utf-8",
            )
            (daily_root / "reports" / "next_research_recommendation.json").write_text(
                json.dumps({"next_step": "continue_daily_opportunity_refinement"}),
                encoding="utf-8",
            )
            (reports_root / "promotion_packet.json").write_text(
                json.dumps({"requires_manual_promotion": True}),
                encoding="utf-8",
            )
            five_year_root = output_root / "five_year_compounding_audit_001"
            (five_year_root / "diagnostics").mkdir(parents=True, exist_ok=True)
            (five_year_root / "status.json").write_text(
                json.dumps({"state": "complete", "classification": "READY_FOR_SMALL_COMPOUNDING", "real_money_allowed": False}),
                encoding="utf-8",
            )
            (five_year_root / "five_year_compounding_summary.json").write_text(
                json.dumps(
                    {
                        "starting_capital": 20000,
                        "ending_capital_under_full_active_capital_model": 26200,
                        "projected_5_year_capital_conservative": 54000,
                        "projected_5_year_capital_base_case": 76000,
                        "projected_5_year_capital_aggressive": 132000,
                        "max_drawdown_pct": 0.19,
                        "worst_day_pnl": -420.0,
                        "best_day_pnl": 860.0,
                        "average_trades_per_day": 3.2,
                        "average_trades_per_active_day": 5.4,
                        "moonshot_5R_plus_count": 4,
                        "moonshot_8R_plus_count": 1,
                        "moonshot_10R_plus_count": 1,
                        "moonshot_profit_contribution_pct": 0.41,
                        "can_3_winners_cover_7_losers": True,
                        "whether_full_active_capital_model_survives_observed_trade_sequence": True,
                        "cooldown_count": 3,
                        "profit_lock_count": 2,
                        "compounding_readiness_classification": "READY_FOR_SMALL_COMPOUNDING",
                        "resolved_at_utc": "2026-06-17T00:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )
            (five_year_root / "five_year_compounding_report.md").write_text(
                "# 5-Year Full Active Capital Long/Short Compounding Replay Audit\n\nResearch-only.\n",
                encoding="utf-8",
            )
            (five_year_root / "diagnostics" / "long_short_compounding_breakdown.csv").write_text(
                "side,trade_count,win_rate,avg_R,total_R,profit_factor,moonshot_5R_plus_count,moonshot_8R_plus_count,moonshot_10R_plus_count\n"
                "long,11,0.45,0.12,1.32,1.08,1,0,0\n"
                "short,12,0.50,0.18,2.16,1.22,3,1,1\n",
                encoding="utf-8",
            )
            (five_year_root / "diagnostics" / "monthly_compounding_summary.csv").write_text(
                "month,starting_equity,ending_equity,monthly_return_pct\n2026-01,20000,21400,0.07\n",
                encoding="utf-8",
            )
            (five_year_root / "diagnostics" / "asymmetric_payoff_report.json").write_text(
                json.dumps({"few_winners_cover_many_losses_count": 2, "moonshot_saved_block_count": 1}),
                encoding="utf-8",
            )
            (five_year_root / "diagnostics" / "moonshot_contribution_report.json").write_text(
                json.dumps({"moonshot_profit_contribution_pct": 0.41}),
                encoding="utf-8",
            )
            (five_year_root / "diagnostics" / "scaling_safety_report.json").write_text(
                json.dumps({"ending_equity_without_profit_vault": 27500, "profit_vault_drag_eur": 1300, "longest_loss_streak": 4, "longest_stop_streak": 3}),
                encoding="utf-8",
            )
            (five_year_root / "diagnostics" / "failure_modes_report.json").write_text(
                json.dumps({"warnings": ["projection_is_extrapolation"]}),
                encoding="utf-8",
            )
            (output_root / "equity.csv").write_text(
                "timestamp,equity\n2026-01-01T00:00:00+00:00,20000\n2026-01-02T00:00:00+00:00,24500\n",
                encoding="utf-8",
            )

            snapshot = load_structural_lab_snapshot(root_dir=root)

            self.assertTrue(snapshot["lab"]["has_run"])
            self.assertEqual(snapshot["overview"]["current_compounding_cycle"], "cycle-3")
            self.assertEqual(snapshot["overview"]["locked_profit"], 3000)
            self.assertEqual(snapshot["overview"]["active_trading_capital"], 20000)
            self.assertEqual(len(snapshot["trade_rows"]), 1)
            self.assertEqual(1, snapshot["trade_frequency_pnl"]["summary"]["current_year_trade_count"])
            self.assertEqual("realized_only", snapshot["trade_frequency_pnl"]["metadata"]["pnl_basis"])
            self.assertTrue(snapshot["artifact_freshness"]["summary"]["exists"])
            self.assertEqual(1, snapshot["research_reports"]["pullback_quality_report"]["count"])
            self.assertEqual(20000, snapshot["five_year_full_capital_audit"]["summary"]["starting_capital"])
            self.assertEqual("READY_FOR_SMALL_COMPOUNDING", snapshot["five_year_full_capital_audit"]["metadata"]["classification"])
            self.assertTrue(snapshot["five_year_full_capital_audit"]["metadata"]["read_only"])
            self.assertEqual(2, len(snapshot["five_year_full_capital_audit"]["long_short_breakdown"]))
            self.assertEqual(12, snapshot["daily_structural_opportunity"]["summary"]["days_analyzed"])
            self.assertEqual(1, len(snapshot["daily_structural_opportunity"]["top_opportunity_by_day"]))
            self.assertEqual("continue_research", snapshot["daily_structural_opportunity"]["metadata"]["classification"])
            self.assertTrue(snapshot["daily_structural_opportunity"]["metadata"]["read_only"])
            self.assertEqual(2, snapshot["daily_structural_opportunity"]["too_tight_report"]["too_tight_day_count"])
            self.assertEqual(3, snapshot["daily_structural_opportunity"]["noise_chasing_report"]["noise_chasing_avoided_count"])
            self.assertEqual(3, snapshot["daily_structural_opportunity"]["summary"]["actual_trade_frequency"]["actual_trade_count"])
            self.assertEqual(2, snapshot["daily_structural_opportunity"]["summary"]["high_R_probe_day_count"])


if __name__ == "__main__":
    unittest.main()
