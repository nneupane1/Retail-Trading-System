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
            long_short_root = output_root / "long_short_edge_repair_audit_001"
            (long_short_root / "diagnostics").mkdir(parents=True, exist_ok=True)
            (long_short_root / "reports").mkdir(parents=True, exist_ok=True)
            (long_short_root / "status.json").write_text(
                json.dumps({"state": "complete", "real_money_allowed": False}),
                encoding="utf-8",
            )
            (long_short_root / "long_short_edge_repair_summary.json").write_text(
                json.dumps(
                    {
                        "resolved_at_utc": "2026-06-17T02:00:00+00:00",
                        "long_trade_count": 11,
                        "short_trade_count": 12,
                        "long_total_R": -3.2,
                        "short_total_R": 4.6,
                        "long_profit_factor": 0.91,
                        "short_profit_factor": 1.24,
                        "long_win_rate": 0.41,
                        "short_win_rate": 0.52,
                        "moonshot_5R_plus_count": 2,
                        "moonshot_profit_contribution_pct_of_net": 1.3,
                        "profit_without_moonshots": -240.0,
                        "profit_with_10R_plus_capped_to_5R": 220.0,
                        "profit_with_all_5R_plus_capped_to_3R": -120.0,
                        "best_long_archetype": "long|sweep_low|strong_convexity|support|failed_breakdown",
                        "worst_long_archetype": "long|sweep_low|elite_convexity|resistance|failed_breakdown",
                        "best_short_archetype": "short|sweep_high|strong_convexity|resistance|failed_breakout",
                        "worst_short_archetype": "short|retest_after_breakdown|elite_convexity|range_high|retest_after_breakdown",
                        "recommended_next_research_patch": "PRESERVE_SHORTS_AND_DISABLE_BAD_LONG_ARCHETYPES",
                    }
                ),
                encoding="utf-8",
            )
            (long_short_root / "long_short_edge_repair_report.md").write_text(
                "# Long vs Short Edge Repair Audit\n\nResearch-only.\n",
                encoding="utf-8",
            )
            (long_short_root / "diagnostics" / "long_edge_breakdown.csv").write_text(
                "setup_pattern,personality_label,entry_context,liquidity_event_type,trade_count,win_rate,avg_R,median_R,total_R,profit_factor,max_winner_R,max_loser_R,loss_count,loss_R_total,high_R_win_count,moonshot_count,moonshot_R_total,drawdown_contribution,gross_pnl,gross_profit_R,gross_loss_R_abs\n"
                "sweep_low,strong_convexity,support,failed_breakdown,5,0.4,-0.1,-0.2,-0.5,0.9,1.8,-1.0,3,-3.0,0,0,0.0,3.0,-80,2.5,2.8\n",
                encoding="utf-8",
            )
            (long_short_root / "diagnostics" / "short_edge_breakdown.csv").write_text(
                "setup_pattern,personality_label,entry_context,liquidity_event_type,trade_count,win_rate,avg_R,median_R,total_R,profit_factor,max_winner_R,max_loser_R,loss_count,loss_R_total,high_R_win_count,moonshot_count,moonshot_R_total,drawdown_contribution,gross_pnl,gross_profit_R,gross_loss_R_abs\n"
                "sweep_high,strong_convexity,resistance,failed_breakout,6,0.5,0.3,0.2,1.8,1.25,4.5,-1.0,3,-3.0,1,1,5.0,3.0,120,4.8,3.0\n",
                encoding="utf-8",
            )
            (long_short_root / "diagnostics" / "archetype_expectancy_breakdown.csv").write_text(
                "side,pullback_type,personality_label,setup_pattern,liquidity_event_type,trade_count,win_rate,avg_R,median_R,total_R,profit_factor,max_winner_R,max_loser_R,high_R_win_count,moonshot_5R_plus_count,moonshot_8R_plus_count,moonshot_10R_plus_count,expectancy_label,recommended_action\n"
                "short,sweep_high,strong_convexity,sweep_high,failed_breakout,6,0.5,0.3,0.2,1.8,1.25,4.5,-1.0,1,1,0,0,KEEP_AND_PRESERVE,preserve_short_archetype\n",
                encoding="utf-8",
            )
            (long_short_root / "diagnostics" / "personality_expectancy_breakdown.csv").write_text(
                "side,personality_label,trade_count,win_rate,avg_R,median_R,total_R,profit_factor,max_winner_R,max_loser_R,loss_count,loss_R_total,high_R_win_count,moonshot_count,moonshot_R_total,drawdown_contribution,gross_pnl,gross_profit_R,gross_loss_R_abs\n"
                "short,strong_convexity,12,0.5,0.2,0.1,2.4,1.2,4.5,-1.0,6,-6.0,1,1,5.0,6.0,140,7.2,6.0\n",
                encoding="utf-8",
            )
            (long_short_root / "diagnostics" / "long_failure_modes.csv").write_text(
                "failure_mode,trade_count,total_R,avg_R,win_rate,profit_factor,evidence_columns,example_trade_ids,recommended_research_action\n"
                "LONG_TINY_STOP_TRAP,3,-3.0,-1.0,0.0,0.0,pattern,trade-1,long_repair:long_tiny_stop_trap\n",
                encoding="utf-8",
            )
            (long_short_root / "diagnostics" / "short_success_modes.csv").write_text(
                "success_mode,trade_count,total_R,avg_R,win_rate,profit_factor,evidence_columns,example_trade_ids,recommended_research_action\n"
                "SHORT_SWEEP_HIGH_REJECTION,4,2.4,0.6,0.5,1.3,pattern,trade-2,short_preserve:short_sweep_high_rejection\n",
                encoding="utf-8",
            )
            (long_short_root / "diagnostics" / "moonshot_repeatability_report.csv").write_text(
                "trade_id,timestamp,side,R,pnl,setup_pattern,pullback_type,personality_label,liquidity_event_type,HTF_context,support_resistance_context,volume_context,VWAP_context,EMA_context,ATR_context,candle_rejection_evidence,was_add_on_used,was_trailing_used,was_profit_lock_used,repeatability_score,moonshot_quality_label\n"
                "trade-3,2026-06-10T00:00:00+00:00,short,5.4,320,sweep_high,sweep_high,strong_convexity,failed_breakout,neutral,resistance,unknown,unknown,aligned,acceptable,text,0,1,1,0.78,REPEATABLE_STRUCTURAL_MOONSHOT\n",
                encoding="utf-8",
            )
            (long_short_root / "diagnostics" / "moonshot_dependency_report.json").write_text(
                json.dumps({"moonshot_5R_plus_count": 2, "net_profit_without_moonshots": -240.0}),
                encoding="utf-8",
            )
            (long_short_root / "diagnostics" / "long_filters_research_candidates.json").write_text(
                json.dumps({"filters": [{"filter_name": "minimum_long_stop_distance_guard"}]}),
                encoding="utf-8",
            )
            (long_short_root / "diagnostics" / "short_preservation_rules.json").write_text(
                json.dumps({"rules": [{"rule_name": "preserve_sweep_high_short_engine"}]}),
                encoding="utf-8",
            )
            (long_short_root / "diagnostics" / "edge_repair_recommendation.json").write_text(
                json.dumps({"recommended_next_research_patch": "PRESERVE_SHORTS_AND_DISABLE_BAD_LONG_ARCHETYPES", "current_problem": "longs_negative_shorts_positive_and_net_edge_is_thin"}),
                encoding="utf-8",
            )
            (long_short_root / "reports" / "next_research_recommendation.json").write_text(
                json.dumps({"recommended_next_patch": "PRESERVE_SHORTS_AND_DISABLE_BAD_LONG_ARCHETYPES"}),
                encoding="utf-8",
            )
            long_damage_root = output_root / "long_damage_control_patch_audit_001"
            (long_damage_root / "diagnostics").mkdir(parents=True, exist_ok=True)
            (long_damage_root / "reports").mkdir(parents=True, exist_ok=True)
            (long_damage_root / "status.json").write_text(
                json.dumps({"state": "complete", "real_money_allowed": False}),
                encoding="utf-8",
            )
            (long_damage_root / "long_damage_control_patch_summary.json").write_text(
                json.dumps(
                    {
                        "resolved_at_utc": "2026-06-17T03:30:00+00:00",
                        "baseline_ending_capital": 18596.55,
                        "best_patch_candidate": "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT",
                        "best_patch_ending_capital": 99334.11,
                        "baseline_profit_factor": 1.0037,
                        "best_patch_profit_factor": 3.8167,
                        "baseline_max_drawdown_pct": 0.3914,
                        "best_patch_max_drawdown_pct": 0.0471,
                        "long_R_removed": 147.59,
                        "short_R_preserved": 45.95,
                        "trade_count_after_patch": 282,
                        "moonshot_dependency_after_patch": "HEALTHY_MOONSHOT_SUPPORT",
                        "readiness_classification_after_patch": "READY_FOR_AGGRESSIVE_RESEARCH_ONLY_COMPOUNDING",
                        "recommended_research_only_patch": "PRESERVE_PROVEN_SHORTS_ONLY",
                    }
                ),
                encoding="utf-8",
            )
            (long_damage_root / "long_damage_control_patch_report.md").write_text(
                "# Long Damage Control Patch Audit\n\nResearch-only.\n",
                encoding="utf-8",
            )
            (long_damage_root / "diagnostics" / "patch_variant_summary.csv").write_text(
                "variant_name,ending_capital,profit_factor,max_drawdown_pct,total_R,moonshot_dependency_label\n"
                "BASELINE_CURRENT_SEQUENCE,18596.55,1.0037,0.3914,1.39,NO_EDGE_WITHOUT_MOONSHOTS\n"
                "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT,99334.11,3.8167,0.0471,166.43,HEALTHY_MOONSHOT_SUPPORT\n",
                encoding="utf-8",
            )
            (long_damage_root / "diagnostics" / "patch_variant_trade_replay.csv").write_text(
                "variant_name,trade_id,side,applied_trade_R,pnl_eur,equity_after_trade\n"
                "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT,trade-1,short,1.5,300,20300\n",
                encoding="utf-8",
            )
            (long_damage_root / "diagnostics" / "disabled_long_archetype_impact.csv").write_text(
                "archetype_or_failure_mode,trade_count_removed,R_removed,ending_capital_after,disable_recommendation,reason\n"
                "LONG_TINY_STOP_TRAP,24,-22.0,55000,disable_in_future_research_patch,long_damage_control_screen\n",
                encoding="utf-8",
            )
            (long_damage_root / "diagnostics" / "preserved_short_edge_impact.csv").write_text(
                "short_success_mode,trade_count,total_R,avg_R,profit_factor,moonshot_count,moonshot_R,drawdown_contribution,preserve_recommendation,reason\n"
                "SHORT_SWEEP_HIGH_REJECTION,24,20.8,0.87,2.4,2,14.0,3.0,PRESERVE,Do not damage SHORT_SWEEP_HIGH_REJECTION unless later evidence contradicts it.\n",
                encoding="utf-8",
            )
            (long_damage_root / "diagnostics" / "moonshot_dependency_after_patch.json").write_text(
                json.dumps(
                    {
                        "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT": {
                            "moonshot_dependency_label": "HEALTHY_MOONSHOT_SUPPORT"
                        }
                    }
                ),
                encoding="utf-8",
            )
            (long_damage_root / "diagnostics" / "full_capital_compounding_after_patch.csv").write_text(
                "variant_name,date,daily_R,daily_pnl,trade_count,equity_end\n"
                "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT,2026-01-01,1.5,300,1,20300\n",
                encoding="utf-8",
            )
            (long_damage_root / "diagnostics" / "drawdown_after_patch.csv").write_text(
                "variant_name,ending_capital,max_drawdown_pct,max_drawdown_eur,worst_day_R,best_day_R\n"
                "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT,99334.11,0.0471,3200,-1.0,8.0\n",
                encoding="utf-8",
            )
            (long_damage_root / "diagnostics" / "best_patch_candidate.json").write_text(
                json.dumps(
                    {
                        "variant_name": "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT",
                        "ending_capital": 99334.11,
                        "profit_factor": 3.8167,
                        "max_drawdown_pct": 0.0471,
                        "total_R": 166.43,
                    }
                ),
                encoding="utf-8",
            )
            (long_damage_root / "diagnostics" / "rejected_patch_candidates.json").write_text(
                json.dumps([{"variant_name": "LONGS_ONLY_BEST_BUCKETS", "rejection_reasons": ["trade_count_too_small"]}]),
                encoding="utf-8",
            )
            (long_damage_root / "diagnostics" / "research_only_patch_recommendation.json").write_text(
                json.dumps({"recommended_research_only_patch": "PRESERVE_PROVEN_SHORTS_ONLY", "real_money_allowed": False}),
                encoding="utf-8",
            )
            (long_damage_root / "reports" / "next_research_recommendation.json").write_text(
                json.dumps({"next_step": "validate_patch_candidate_only_in_research"}),
                encoding="utf-8",
            )
            frozen_validation_root = output_root / "frozen_patch_validation_audit_001"
            (frozen_validation_root / "diagnostics").mkdir(parents=True, exist_ok=True)
            (frozen_validation_root / "reports").mkdir(parents=True, exist_ok=True)
            (frozen_validation_root / "status.json").write_text(
                json.dumps({"state": "complete", "real_money_allowed": False}),
                encoding="utf-8",
            )
            (frozen_validation_root / "frozen_patch_validation_summary.json").write_text(
                json.dumps(
                    {
                        "resolved_at_utc": "2026-06-17T04:30:00+00:00",
                        "frozen_patch_candidate": "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT",
                        "validation_window_count": 3,
                        "year_window_pass_count": 2,
                        "year_window_fail_count": 1,
                        "walk_forward_pass_rate": 0.66,
                        "best_validation_window": "2023",
                        "worst_validation_window": "2021",
                        "validation_ending_capital": 41200.0,
                        "max_validation_drawdown": 0.18,
                        "moonshot_dependency_in_validation": "MODERATE_MOONSHOT_DEPENDENCY",
                        "profit_without_moonshots_in_validation": 4200.0,
                        "promotion_gate_classification": "PROMISING_NEEDS_WALK_FORWARD",
                        "recommended_next_action": "continue_research_only_with_frozen_patch_and_collect_truer_out_of_sample_evidence",
                    }
                ),
                encoding="utf-8",
            )
            (frozen_validation_root / "frozen_patch_validation_report.md").write_text(
                "# Frozen Patch Multi-Year Validation Audit\n\nResearch-only.\n",
                encoding="utf-8",
            )
            (frozen_validation_root / "diagnostics" / "frozen_patch_rules.json").write_text(
                json.dumps({"frozen_patch_candidate": "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT", "real_money_allowed": False}),
                encoding="utf-8",
            )
            (frozen_validation_root / "diagnostics" / "validation_window_summary.csv").write_text(
                "window_name,trade_count,ending_capital_from_20000,profit_factor,max_drawdown_pct,validation_label\n"
                "FULL_AVAILABLE_HISTORY_FROZEN_PATCH,120,41200,1.41,0.18,PASS_ACCEPTABLE\n",
                encoding="utf-8",
            )
            (frozen_validation_root / "diagnostics" / "year_by_year_validation.csv").write_text(
                "window_name,trade_count,ending_capital_from_20000,profit_factor,max_drawdown_pct,validation_label\n"
                "2021,12,18500,0.94,0.22,FAIL_NO_EDGE\n"
                "2022,24,24500,1.32,0.11,PASS_ACCEPTABLE\n"
                "2023,36,31800,1.58,0.09,PASS_STRONG\n",
                encoding="utf-8",
            )
            (frozen_validation_root / "diagnostics" / "regime_validation_summary.csv").write_text(
                "regime,trade_count,total_R,profit_factor,max_drawdown_pct,long_total_R,short_total_R,moonshot_dependency,validation_label\n"
                "BULL_TREND,24,10.2,1.32,0.11,10.2,0.0,0.25,PASS_ACCEPTABLE\n",
                encoding="utf-8",
            )
            (frozen_validation_root / "diagnostics" / "walk_forward_validation.csv").write_text(
                "train_start,train_end,test_start,test_end,test_trade_count,test_total_R,test_profit_factor,test_max_drawdown_pct,test_ending_capital,test_validation_label,frozen_rules_applied_unchanged\n"
                "2021-01-01,2021-12-31,2022-01-01,2022-06-30,10,6.1,1.30,0.12,23200,PASS_ACCEPTABLE,True\n",
                encoding="utf-8",
            )
            (frozen_validation_root / "diagnostics" / "out_of_sample_validation.csv").write_text(
                "window_name,test_start,test_end,test_trade_count,test_total_R,test_profit_factor,test_max_drawdown_pct,test_validation_label,note\n"
                "RETROSPECTIVE_LAST_12M,2023-01-01,2023-12-31,36,14.2,1.58,0.09,PASS_STRONG,retrospective_holdout_using_frozen_patch_rules\n",
                encoding="utf-8",
            )
            (frozen_validation_root / "diagnostics" / "frozen_patch_trade_replay.csv").write_text(
                "variant_name,trade_id,side,applied_trade_R,pnl_eur,equity_after_trade\n"
                "FULL_AVAILABLE_HISTORY_FROZEN_PATCH,trade-1,short,1.5,300,20300\n",
                encoding="utf-8",
            )
            (frozen_validation_root / "diagnostics" / "full_active_capital_validation_curve.csv").write_text(
                "variant_name,date,daily_R,daily_pnl,trade_count,equity_end\n"
                "FULL_AVAILABLE_HISTORY_FROZEN_PATCH,2023-01-01,1.5,300,1,20300\n",
                encoding="utf-8",
            )
            (frozen_validation_root / "diagnostics" / "drawdown_validation_report.csv").write_text(
                "window_name,ending_capital,max_drawdown_pct,worst_day_R,best_day_R,validation_label\n"
                "FULL_AVAILABLE_HISTORY_FROZEN_PATCH,41200,0.18,-1.0,6.0,PASS_ACCEPTABLE\n",
                encoding="utf-8",
            )
            (frozen_validation_root / "diagnostics" / "moonshot_dependency_validation.json").write_text(
                json.dumps({"FULL_AVAILABLE_HISTORY_FROZEN_PATCH": {"moonshot_dependency_label": "MODERATE_MOONSHOT_DEPENDENCY"}}),
                encoding="utf-8",
            )
            (frozen_validation_root / "diagnostics" / "long_short_validation_breakdown.csv").write_text(
                "window_name,side,trade_count,total_R,profit_factor\n"
                "FULL_AVAILABLE_HISTORY_FROZEN_PATCH,long,40,12.1,1.22\n"
                "FULL_AVAILABLE_HISTORY_FROZEN_PATCH,short,80,18.3,1.44\n",
                encoding="utf-8",
            )
            (frozen_validation_root / "diagnostics" / "validation_failure_modes.csv").write_text(
                "window_name,validation_label,reason,trade_count,profit_factor,total_R\n"
                "2021,FAIL_NO_EDGE,expectancy_failed,12,0.94,-2.1\n",
                encoding="utf-8",
            )
            (frozen_validation_root / "diagnostics" / "promotion_gate_report.json").write_text(
                json.dumps({"classification": "PROMISING_NEEDS_WALK_FORWARD", "real_money_allowed": False, "true_unseen_proof_available": False}),
                encoding="utf-8",
            )
            (frozen_validation_root / "reports" / "next_research_recommendation.json").write_text(
                json.dumps({"recommended_next_action": "continue_research_only_with_frozen_patch_and_collect_truer_out_of_sample_evidence"}),
                encoding="utf-8",
            )
            frozen_forensic_root = output_root / "frozen_patch_forensic_integrity_audit_001"
            (frozen_forensic_root / "diagnostics").mkdir(parents=True, exist_ok=True)
            (frozen_forensic_root / "reports").mkdir(parents=True, exist_ok=True)
            (frozen_forensic_root / "status.json").write_text(
                json.dumps({"state": "complete", "real_money_allowed": False}),
                encoding="utf-8",
            )
            (frozen_forensic_root / "forensic_integrity_summary.json").write_text(
                json.dumps(
                    {
                        "resolved_at_utc": "2026-06-17T05:30:00+00:00",
                        "current_proof_status": ["CURRENT_SAMPLE_REPLAY_ONLY", "RETROSPECTIVE_PATCH_VALIDATION", "PARTIAL_YEAR_VALIDATION"],
                        "current_proof_status_label": "CURRENT_SAMPLE_REPLAY_ONLY / RETROSPECTIVE_PATCH_VALIDATION / PARTIAL_YEAR_VALIDATION",
                        "trade_artifact_date_range": {"start": "2025-12-14T02:00:00", "end": "2026-06-13T00:00:00"},
                        "available_trade_years": [2025, 2026],
                        "available_source_years": [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026],
                        "true_unseen_proof_available": False,
                        "current_validation_reused_discovery_sample": True,
                        "sample_reuse_risk": "HIGH",
                        "leakage_overfit_risk": "HIGH",
                        "next_required_validation": "generate broad BTC structural outputs then rerun frozen-rule validation",
                        "promotion_blockers": ["only_2025_2026_real_trade_coverage", "same_sample_validation"],
                        "promotion_blocker_count": 2,
                        "what_is_proven": ["candidate looks strong on current sample"],
                        "what_is_not_proven": ["no true unseen proof"],
                    }
                ),
                encoding="utf-8",
            )
            (frozen_forensic_root / "forensic_integrity_report.md").write_text(
                "# Frozen Patch Forensic Validation Integrity Audit\n\nResearch-only.\n",
                encoding="utf-8",
            )
            (frozen_forensic_root / "diagnostics" / "artifact_lineage_report.json").write_text(
                json.dumps({"same_trade_artifact_used_for_discovery_and_validation": True}),
                encoding="utf-8",
            )
            (frozen_forensic_root / "diagnostics" / "data_coverage_report.json").write_text(
                json.dumps(
                    {
                        "available_trade_start": "2025-12-14T02:00:00",
                        "available_trade_end": "2026-06-13T00:00:00",
                        "raw_source_history_sufficient_to_regenerate": True,
                        "coverage_is_sufficient_for_multi_year_validation": False,
                    }
                ),
                encoding="utf-8",
            )
            (frozen_forensic_root / "diagnostics" / "sample_reuse_report.json").write_text(
                json.dumps({"current_validation_is_retrospective_only": True}),
                encoding="utf-8",
            )
            (frozen_forensic_root / "diagnostics" / "leakage_risk_report.json").write_text(
                json.dumps({"risk_level": "HIGH", "validation_windows_effectively_independent": False}),
                encoding="utf-8",
            )
            (frozen_forensic_root / "diagnostics" / "frozen_rule_origin_report.json").write_text(
                json.dumps({"selected_variant": "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT"}),
                encoding="utf-8",
            )
            (frozen_forensic_root / "diagnostics" / "source_history_availability_report.json").write_text(
                json.dumps({"safe_replay_possible_now": True}),
                encoding="utf-8",
            )
            (frozen_forensic_root / "diagnostics" / "validation_gap_report.json").write_text(
                json.dumps({"minimum_next_validation_needed": "broad replay first", "why_1m_target_is_not_yet_proven": "sample too narrow"}),
                encoding="utf-8",
            )
            (frozen_forensic_root / "diagnostics" / "required_next_replay_plan.json").write_text(
                json.dumps({"stage_1_generate_broad_historical_structural_outputs": {"purpose": "broad replay"}}),
                encoding="utf-8",
            )
            (frozen_forensic_root / "diagnostics" / "no_go_risks.json").write_text(
                json.dumps({"blockers": ["only_2025_2026_real_trade_coverage", "same_sample_validation"], "promotion_blocker_count": 2}),
                encoding="utf-8",
            )
            (frozen_forensic_root / "reports" / "next_research_recommendation.json").write_text(
                json.dumps({"readme_note_recommendation": "next requirement = broad historical replay with frozen rules"}),
                encoding="utf-8",
            )
            broad_replay_root = output_root / "broad_historical_structural_replay_001"
            (broad_replay_root / "diagnostics").mkdir(parents=True, exist_ok=True)
            (broad_replay_root / "reports").mkdir(parents=True, exist_ok=True)
            (broad_replay_root / "status.json").write_text(
                json.dumps({"state": "complete", "resolved_at_utc": "2026-06-17T06:00:00+00:00", "real_money_allowed": False}),
                encoding="utf-8",
            )
            (broad_replay_root / "broad_historical_replay_summary.json").write_text(
                json.dumps(
                    {
                        "resolved_at_utc": "2026-06-17T06:00:00+00:00",
                        "research_only": True,
                        "real_money_allowed": False,
                        "source_data_start": "2018-01-01T00:00:00",
                        "source_data_end": "2026-06-13T00:00:00",
                        "generated_ledger_start": "2018-01-01T01:00:00",
                        "generated_ledger_end": "2026-06-13T00:00:00",
                        "years_generated": ["2018", "2019", "2020"],
                        "trade_count": 42,
                        "long_trade_count": 19,
                        "short_trade_count": 23,
                        "coverage_sufficient_for_frozen_patch_validation": True,
                        "ledger_output_path": str(broad_replay_root / "ledger"),
                        "next_required_step": "APPLY_FROZEN_PATCH_TO_BROAD_HISTORICAL_LEDGER",
                    }
                ),
                encoding="utf-8",
            )
            (broad_replay_root / "broad_historical_replay_report.md").write_text(
                "# Broad Historical Structural Replay 001\n\nResearch-only.\n",
                encoding="utf-8",
            )
            (broad_replay_root / "diagnostics" / "source_data_coverage.json").write_text(
                json.dumps(
                    {
                        "source_data_start": "2018-01-01T00:00:00",
                        "source_data_end": "2026-06-13T00:00:00",
                        "source_path": "data_storage/BTCUSDT/1m/BTCUSDT_1m_2018-01-01_to_2026-06-13.csv",
                        "cleaned_rows": 1000,
                        "missing_timestamp_count": 12,
                        "duplicate_timestamp_count": 2,
                    }
                ),
                encoding="utf-8",
            )
            (broad_replay_root / "diagnostics" / "replay_window_manifest.json").write_text(
                json.dumps({"windows": [{"window_name": "2018", "trades_generated": 5}]}),
                encoding="utf-8",
            )
            (broad_replay_root / "diagnostics" / "yearly_trade_counts.csv").write_text(
                "period,trade_count,long_trade_count,short_trade_count,setup_count\n2018,5,2,3,11\n",
                encoding="utf-8",
            )
            (broad_replay_root / "diagnostics" / "monthly_trade_counts.csv").write_text(
                "period,trade_count,long_trade_count,short_trade_count\n2018-01,2,1,1\n",
                encoding="utf-8",
            )
            (broad_replay_root / "diagnostics" / "replay_health_report.json").write_text(
                json.dumps({"successful_replay": True, "safe_for_frozen_patch_validation": True, "generated_trade_years": [2018, 2019], "zero_trade_windows": []}),
                encoding="utf-8",
            )
            (broad_replay_root / "diagnostics" / "replay_failure_report.json").write_text(
                json.dumps({"failed_stage": None}),
                encoding="utf-8",
            )
            (broad_replay_root / "diagnostics" / "data_gap_report.json").write_text(
                json.dumps({"total_missing_minutes": 12}),
                encoding="utf-8",
            )
            (broad_replay_root / "diagnostics" / "no_future_leakage_checks.json").write_text(
                json.dumps({"counts": {"passed": 5, "failed": 0, "unknown": 1}}),
                encoding="utf-8",
            )
            (broad_replay_root / "diagnostics" / "generated_ledger_manifest.json").write_text(
                json.dumps({"current_short_window_artifacts_untouched": True, "broad_replay_isolated": True}),
                encoding="utf-8",
            )
            (broad_replay_root / "reports" / "next_research_recommendation.json").write_text(
                json.dumps({"next_step": "APPLY_FROZEN_PATCH_TO_BROAD_HISTORICAL_LEDGER"}),
                encoding="utf-8",
            )
            broad_frozen_patch_root = output_root / "broad_frozen_patch_validation_001"
            (broad_frozen_patch_root / "diagnostics").mkdir(parents=True, exist_ok=True)
            (broad_frozen_patch_root / "reports").mkdir(parents=True, exist_ok=True)
            (broad_frozen_patch_root / "status.json").write_text(
                json.dumps({"state": "complete", "real_money_allowed": False}),
                encoding="utf-8",
            )
            (broad_frozen_patch_root / "broad_frozen_patch_summary.json").write_text(
                json.dumps(
                    {
                        "resolved_at_utc": "2026-06-17T06:30:00+00:00",
                        "research_only": True,
                        "real_money_allowed": False,
                        "behavior_change_allowed": False,
                        "raw_broad_ending_equity": 80028.55,
                        "patched_broad_ending_equity": 92100.12,
                        "raw_broad_profit_factor": 1.1427,
                        "patched_broad_profit_factor": 1.33,
                        "raw_broad_max_drawdown_pct": 0.2163,
                        "patched_broad_max_drawdown_pct": 0.171,
                        "raw_broad_trade_count": 5649,
                        "patched_broad_trade_count": 2910,
                        "long_R_removed": -48.2,
                        "short_R_preserved": 122.4,
                        "moonshot_dependency_verdict": "HEALTHY_MOONSHOT_SUPPORT",
                        "execution_cost_verdict": "reduced_trade_count_improves_cost_survival",
                        "final_patch_classification": "PATCH_IMPROVES_BUT_NOT_COST_SURVIVABLE",
                        "next_recommended_step": "repair_execution_realism_and_trade_density_before_any_promotion_review",
                        "yearly_verdict": {"years_helped": 6, "years_hurt": 2, "yearly_consistency_label": "mostly_consistent"},
                    }
                ),
                encoding="utf-8",
            )
            (broad_frozen_patch_root / "broad_frozen_patch_report.md").write_text(
                "# Broad Frozen Patch Validation\n\nResearch-only.\n",
                encoding="utf-8",
            )
            (broad_frozen_patch_root / "diagnostics" / "raw_vs_frozen_patch_comparison.json").write_text(
                json.dumps({"raw_broad_actual": {"ending_equity": 80028.55}, "patched_broad_proxy_replay": {"ending_capital": 92100.12}}),
                encoding="utf-8",
            )
            (broad_frozen_patch_root / "diagnostics" / "raw_vs_frozen_patch_comparison.csv").write_text(
                "variant,ending_equity,profit_factor,avg_R,max_drawdown_pct,trade_count\nraw_broad_actual,80028.55,1.1427,0.0237,0.2163,5649\npatched_broad_proxy_replay,92100.12,1.33,0.08,0.171,2910\n",
                encoding="utf-8",
            )
            (broad_frozen_patch_root / "diagnostics" / "yearly_raw_vs_patch.csv").write_text(
                "year,raw_pnl,patched_pnl,raw_profit_factor,patched_profit_factor,raw_total_R,patched_total_R,raw_max_drawdown_pct,patched_max_drawdown_pct,raw_trade_count,patched_trade_count,raw_long_contribution_R,patched_long_contribution_R,raw_short_contribution_R,patched_short_contribution_R,patch_helped_or_hurt\n2021,1000,1400,1.1,1.2,5.0,6.5,0.18,0.14,100,60,2.0,1.0,3.0,5.5,helped\n",
                encoding="utf-8",
            )
            (broad_frozen_patch_root / "diagnostics" / "monthly_raw_vs_patch.csv").write_text(
                "month,raw_total_R,patch_total_R,raw_total_pnl,patch_total_pnl,raw_ending_equity,patch_ending_equity,patch_helped\n2021-01,1.0,1.2,100,120,20100,20120,True\n",
                encoding="utf-8",
            )
            (broad_frozen_patch_root / "diagnostics" / "long_short_raw_vs_patch.json").write_text(
                json.dumps({"raw_longs_net_damaging": True, "raw_shorts_carry_edge": True}),
                encoding="utf-8",
            )
            (broad_frozen_patch_root / "diagnostics" / "archetype_raw_vs_patch.csv").write_text(
                "archetype_key,raw_trade_count,patched_trade_count,raw_total_R,patched_total_R,raw_avg_R,patched_avg_R,raw_profit_factor,patched_profit_factor\nshort|sweep_high|elite_convexity|resistance|equal_highs,24,24,30,30,1.25,1.25,1.4,1.4\n",
                encoding="utf-8",
            )
            (broad_frozen_patch_root / "diagnostics" / "disabled_trade_impact.csv").write_text(
                "failure_mode_or_reason,archetype_key,side,removed_trade_count,removed_total_R,removed_total_pnl,removed_moonshot_count\nLONG_TINY_STOP_TRAP,long|sweep_low|strong_convexity|support|failed_breakdown,long,18,-18,-1800,0\n",
                encoding="utf-8",
            )
            (broad_frozen_patch_root / "diagnostics" / "preserved_trade_impact.csv").write_text(
                "short_success_mode,archetype_key,preserved_trade_count,preserved_total_R,preserved_total_pnl,preserved_moonshot_count\nSHORT_SWEEP_HIGH_REJECTION,short|sweep_high|elite_convexity|resistance|equal_highs,24,30,3000,2\n",
                encoding="utf-8",
            )
            (broad_frozen_patch_root / "diagnostics" / "moonshot_dependency_broad_patch.json").write_text(
                json.dumps({"patched": {"classification": "HEALTHY_MOONSHOT_SUPPORT"}}),
                encoding="utf-8",
            )
            (broad_frozen_patch_root / "diagnostics" / "execution_cost_sensitivity_broad_patch.json").write_text(
                json.dumps({"scenarios": {"low_cost": {"patch_improves_cost_survival": True}}}),
                encoding="utf-8",
            )
            (broad_frozen_patch_root / "diagnostics" / "drawdown_comparison.csv").write_text(
                "date,raw_equity_end,patched_equity_end,raw_drawdown_pct,patched_drawdown_pct\n2021-01-01,20000,20000,0,0\n",
                encoding="utf-8",
            )
            (broad_frozen_patch_root / "diagnostics" / "profit_vault_comparison.json").write_text(
                json.dumps({"raw_broad_profit_vault": {"base_capital": 20000}, "patched_replay_proxy": {"native_profit_vault_replayed": False}}),
                encoding="utf-8",
            )
            (broad_frozen_patch_root / "diagnostics" / "patch_survival_by_year.json").write_text(
                json.dumps({"years_helped": 6, "years_hurt": 2, "yearly_consistency_label": "mostly_consistent"}),
                encoding="utf-8",
            )
            (broad_frozen_patch_root / "diagnostics" / "no_go_risks.json").write_text(
                json.dumps({"blockers": ["patch_remains_destroyed_after_low_cost_assumptions"], "promotion_blocker_count": 1}),
                encoding="utf-8",
            )
            (broad_frozen_patch_root / "reports" / "next_research_recommendation.json").write_text(
                json.dumps({"next_step": "repair_execution_realism_and_trade_density_before_any_promotion_review"}),
                encoding="utf-8",
            )
            native_strict_root = output_root / "native_sr_aware_strict_stress_monte_carlo_audit_001"
            (native_strict_root / "diagnostics").mkdir(parents=True, exist_ok=True)
            (native_strict_root / "reports").mkdir(parents=True, exist_ok=True)
            (native_strict_root / "status.json").write_text(
                json.dumps({"state": "complete", "resolved_at_utc": "2026-06-18T09:00:00+00:00", "real_money_allowed": False}),
                encoding="utf-8",
            )
            (native_strict_root / "native_sr_aware_strict_stress_monte_carlo_summary.json").write_text(
                json.dumps(
                    {
                        "resolved_at_utc": "2026-06-18T09:00:00+00:00",
                        "research_only": True,
                        "real_money_allowed": False,
                        "variant_name": "NATIVE_SR_AWARE_STRICT",
                        "trade_count": 558,
                        "normal_ending_equity": 3303577.61,
                        "normal_profit_factor": 42.570307,
                        "normal_avg_R": 1.645417,
                        "normal_max_drawdown_pct": 0.0143,
                        "rolling_5y_average_ending_equity": 505632.58,
                        "rolling_5y_median_ending_equity": 499590.19,
                        "pf_sanity_verdict": "PF_VALID_BUT_FRAGILE",
                        "pre_entry_integrity_verdict": "NO_LEAKAGE_DETECTED",
                        "monte_carlo_reference_mode": "monthly_block_bootstrap",
                        "monte_carlo_simulation_count": 5000,
                        "promotion_gate_classification": "PROMISING_BUT_NOT_MISSION_MOVING",
                        "mission_gap_verdict": "looks_like_500k_but_not_1m_in_5y",
                        "next_research_action": "continue research only",
                    }
                ),
                encoding="utf-8",
            )
            (native_strict_root / "native_sr_aware_strict_stress_monte_carlo_report.md").write_text(
                "# Native SR-Aware Strict Variant Stress + Monte Carlo Validation Audit\n\nResearch-only.\n",
                encoding="utf-8",
            )
            (native_strict_root / "diagnostics" / "frozen_variant_spec.json").write_text(
                json.dumps({"variant_name": "NATIVE_SR_AWARE_STRICT", "trade_count": 558, "profit_factor": 42.570307, "research_only": True, "real_money_allowed": False}),
                encoding="utf-8",
            )
            (native_strict_root / "diagnostics" / "pf_42_sanity_audit.json").write_text(
                json.dumps({"classification": "PF_VALID_BUT_FRAGILE", "cost_inclusive_profit_factor_15bps": 7.2, "research_only": True}),
                encoding="utf-8",
            )
            (native_strict_root / "diagnostics" / "pre_entry_rule_integrity_audit.json").write_text(
                json.dumps({"classification": "NO_LEAKAGE_DETECTED", "research_only": True}),
                encoding="utf-8",
            )
            (native_strict_root / "diagnostics" / "stress_test_matrix.csv").write_text(
                "scenario,ending_equity,mission_label\nnormal,3303577.61,MISSION_STRONG\nfive_x_cost,412000.00,MISSION_SURVIVES_BUT_BELOW_1M\n",
                encoding="utf-8",
            )
            (native_strict_root / "diagnostics" / "rolling_5y_stress_summary.csv").write_text(
                "window_start,window_end,scenario,ending_equity,mission_label\n2021-01-01,2025-12-31,normal,505632.58,MISSION_PROMISING\n",
                encoding="utf-8",
            )
            (native_strict_root / "diagnostics" / "monte_carlo_summary.json").write_text(
                json.dumps(
                    {
                        "research_only": True,
                        "modes": {
                            "monthly_block_bootstrap": {
                                "simulation_count": 5000,
                                "median_ending_equity": 521000.0,
                                "p25_ending_equity": 188000.0,
                                "probability_end_above_500k": 0.53,
                                "probability_end_above_1m": 0.07,
                                "probability_ruin_or_equity_below_50pct_start": 0.01,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            (native_strict_root / "diagnostics" / "monte_carlo_distribution.csv").write_text(
                "mode,simulation_id,ending_equity\nmonthly_block_bootstrap,1,521000.0\n",
                encoding="utf-8",
            )
            (native_strict_root / "diagnostics" / "monte_carlo_drawdown_distribution.csv").write_text(
                "mode,simulation_id,max_drawdown_pct,longest_loss_streak,min_equity\nmonthly_block_bootstrap,1,0.11,4,18500\n",
                encoding="utf-8",
            )
            (native_strict_root / "diagnostics" / "monte_carlo_ruin_risk.json").write_text(
                json.dumps({"research_only": True, "modes": {"monthly_block_bootstrap": {"probability_ruin_or_equity_below_50pct_start": 0.01}}}),
                encoding="utf-8",
            )
            (native_strict_root / "diagnostics" / "mission_gap_report.json").write_text(
                json.dumps({"verdict": "looks_like_500k_but_not_1m_in_5y", "median_5y_gap_to_1m": 500409.81, "research_only": True}),
                encoding="utf-8",
            )
            (native_strict_root / "diagnostics" / "promotion_gate_report.json").write_text(
                json.dumps({"classification": "PROMISING_BUT_NOT_MISSION_MOVING", "real_money_allowed": False, "research_only": True}),
                encoding="utf-8",
            )
            (native_strict_root / "reports" / "next_research_recommendation.json").write_text(
                json.dumps({"next_action": "continue research only", "research_only": True}),
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
            self.assertEqual(-3.2, snapshot["long_short_edge_repair"]["summary"]["long_total_R"])
            self.assertEqual(4.6, snapshot["long_short_edge_repair"]["summary"]["short_total_R"])
            self.assertEqual(
                "PRESERVE_SHORTS_AND_DISABLE_BAD_LONG_ARCHETYPES",
                snapshot["long_short_edge_repair"]["edge_repair_recommendation"]["recommended_next_research_patch"],
            )
            self.assertTrue(snapshot["long_short_edge_repair"]["metadata"]["read_only"])
            self.assertEqual(1, len(snapshot["long_short_edge_repair"]["moonshot_repeatability"]))
            self.assertEqual(
                "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT",
                snapshot["long_damage_control_patch"]["summary"]["best_patch_candidate"],
            )
            self.assertEqual(
                "PRESERVE_PROVEN_SHORTS_ONLY",
                snapshot["long_damage_control_patch"]["research_only_patch_recommendation"]["recommended_research_only_patch"],
            )
            self.assertTrue(snapshot["long_damage_control_patch"]["metadata"]["read_only"])
            self.assertEqual(
                "HEALTHY_MOONSHOT_SUPPORT",
                snapshot["long_damage_control_patch"]["moonshot_dependency_after_patch"]["BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT"]["moonshot_dependency_label"],
            )
            self.assertEqual(2, len(snapshot["long_damage_control_patch"]["patch_variant_summary"]))
            self.assertEqual(
                "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT",
                snapshot["frozen_patch_validation"]["summary"]["frozen_patch_candidate"],
            )
            self.assertEqual(
                "PROMISING_NEEDS_WALK_FORWARD",
                snapshot["frozen_patch_validation"]["promotion_gate_report"]["classification"],
            )
            self.assertTrue(snapshot["frozen_patch_validation"]["metadata"]["read_only"])
            self.assertEqual(1, len(snapshot["frozen_patch_validation"]["validation_window_summary"]))
            self.assertEqual(3, len(snapshot["frozen_patch_validation"]["year_by_year_validation"]))
            self.assertEqual(
                "CURRENT_SAMPLE_REPLAY_ONLY / RETROSPECTIVE_PATCH_VALIDATION / PARTIAL_YEAR_VALIDATION",
                snapshot["frozen_patch_forensic_integrity"]["summary"]["current_proof_status_label"],
            )
            self.assertEqual("HIGH", snapshot["frozen_patch_forensic_integrity"]["leakage_risk"]["risk_level"])
            self.assertTrue(snapshot["frozen_patch_forensic_integrity"]["artifact_lineage"]["same_trade_artifact_used_for_discovery_and_validation"])
            self.assertTrue(snapshot["frozen_patch_forensic_integrity"]["metadata"]["read_only"])
            self.assertEqual(2, snapshot["frozen_patch_forensic_integrity"]["no_go_risks"]["promotion_blocker_count"])
            self.assertEqual(42, snapshot["broad_historical_structural_replay"]["summary"]["trade_count"])
            self.assertTrue(snapshot["broad_historical_structural_replay"]["replay_health_report"]["successful_replay"])
            self.assertTrue(snapshot["broad_historical_structural_replay"]["generated_ledger_manifest"]["broad_replay_isolated"])
            self.assertTrue(snapshot["broad_historical_structural_replay"]["metadata"]["read_only"])
            self.assertEqual("APPLY_FROZEN_PATCH_TO_BROAD_HISTORICAL_LEDGER", snapshot["broad_historical_structural_replay"]["next_research_recommendation"]["next_step"])
            self.assertEqual(80028.55, snapshot["broad_frozen_patch_validation"]["summary"]["raw_broad_ending_equity"])
            self.assertEqual("PATCH_IMPROVES_BUT_NOT_COST_SURVIVABLE", snapshot["broad_frozen_patch_validation"]["summary"]["final_patch_classification"])
            self.assertTrue(snapshot["broad_frozen_patch_validation"]["metadata"]["read_only"])
            self.assertEqual(1, len(snapshot["broad_frozen_patch_validation"]["yearly_raw_vs_patch"]))
            self.assertTrue(snapshot["broad_frozen_patch_validation"]["execution_cost_sensitivity"]["scenarios"]["low_cost"]["patch_improves_cost_survival"])
            self.assertEqual(1, snapshot["broad_frozen_patch_validation"]["no_go_risks"]["promotion_blocker_count"])
            self.assertEqual("NATIVE_SR_AWARE_STRICT", snapshot["native_sr_aware_strict_stress_monte_carlo"]["summary"]["variant_name"])
            self.assertEqual("PF_VALID_BUT_FRAGILE", snapshot["native_sr_aware_strict_stress_monte_carlo"]["pf_42_sanity"]["classification"])
            self.assertEqual("NO_LEAKAGE_DETECTED", snapshot["native_sr_aware_strict_stress_monte_carlo"]["pre_entry_rule_integrity"]["classification"])
            self.assertEqual(
                "PROMISING_BUT_NOT_MISSION_MOVING",
                snapshot["native_sr_aware_strict_stress_monte_carlo"]["promotion_gate_report"]["classification"],
            )
            self.assertTrue(snapshot["native_sr_aware_strict_stress_monte_carlo"]["metadata"]["read_only"])
            self.assertEqual(
                5000,
                snapshot["native_sr_aware_strict_stress_monte_carlo"]["monte_carlo_summary"]["modes"]["monthly_block_bootstrap"]["simulation_count"],
            )


if __name__ == "__main__":
    unittest.main()
