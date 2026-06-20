import csv
import json
import tempfile
import unittest
from pathlib import Path

from structural_compounding_lab.diagnostics.frozen_patch_forensic_integrity_audit import (
    FrozenPatchForensicIntegrityAuditConfig,
    write_frozen_patch_forensic_integrity_audit,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


class FrozenPatchForensicIntegrityAuditTests(unittest.TestCase):
    def test_forensic_audit_detects_same_sample_validation_and_missing_unseen_proof(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / "structural_compounding_lab"
            output_root = package_root / "output"
            output_root.mkdir(parents=True, exist_ok=True)
            config_root = package_root / "config"
            config_root.mkdir(parents=True, exist_ok=True)

            (config_root / "structural_compounding_settings.json").write_text(
                json.dumps(
                    {
                        "symbol": "BTCUSDT",
                        "execution_timeframe": "1h",
                        "data": {
                            "base_path": "../data_storage",
                            "default_interval": "1m",
                            "history_start_date": "2018-01-01",
                            "history_end_date": "2026-06-13",
                        },
                    }
                ),
                encoding="utf-8",
            )
            (config_root / "structural_compounding_settings.yaml").write_text("lab_name: Structural Compounding Lab\n", encoding="utf-8")
            (config_root / "symbols.json").write_text(json.dumps({"symbols": ["BTCUSDT"]}), encoding="utf-8")
            (config_root / "validation_ladder.json").write_text(json.dumps({"stages": ["smoke", "holdout"]}), encoding="utf-8")

            _write_csv(
                output_root / "trades.csv",
                [
                    {
                        "trade_id": "t1",
                        "symbol": "BTCUSDT",
                        "side": "long",
                        "entry_time": "2025-12-14T02:00:00",
                        "exit_time": "2025-12-15T02:00:00",
                        "entry_price": 100,
                        "exit_price": 104,
                        "initial_stop": 99,
                        "trail_stop": 99,
                        "pnl": 200,
                        "r_multiple": 2.0,
                        "entry_reason": "A setup: sweep_low near support with RR 3.0 and HTF bias bullish.",
                        "exit_reason": "target_hit",
                        "holding_bars": 4,
                        "setup_class": "A",
                        "strategy_type": "structural_compounding",
                        "moonshot_state": "normal",
                        "entry_score": 4.1,
                        "risk_multiplier": 1.1,
                        "convexity_label": "strong_convexity",
                    },
                    {
                        "trade_id": "t2",
                        "symbol": "BTCUSDT",
                        "side": "short",
                        "entry_time": "2026-03-01T02:00:00",
                        "exit_time": "2026-03-02T02:00:00",
                        "entry_price": 100,
                        "exit_price": 92,
                        "initial_stop": 101,
                        "trail_stop": 101,
                        "pnl": 800,
                        "r_multiple": 8.0,
                        "entry_reason": "A setup: sweep_high near resistance with RR 9.0 and HTF bias bearish.",
                        "exit_reason": "moonshot_capture",
                        "holding_bars": 8,
                        "setup_class": "A",
                        "strategy_type": "structural_compounding",
                        "moonshot_state": "moonshot",
                        "entry_score": 4.5,
                        "risk_multiplier": 1.15,
                        "convexity_label": "elite_convexity",
                    },
                    {
                        "trade_id": "t3",
                        "symbol": "BTCUSDT",
                        "side": "short",
                        "entry_time": "2026-06-12T02:00:00",
                        "exit_time": "2026-06-13T00:00:00",
                        "entry_price": 100,
                        "exit_price": 98,
                        "initial_stop": 101,
                        "trail_stop": 101,
                        "pnl": 200,
                        "r_multiple": 2.0,
                        "entry_reason": "A setup: sweep_high near resistance with RR 3.0 and HTF bias bearish.",
                        "exit_reason": "target_hit",
                        "holding_bars": 3,
                        "setup_class": "A",
                        "strategy_type": "structural_compounding",
                        "moonshot_state": "normal",
                        "entry_score": 4.0,
                        "risk_multiplier": 1.05,
                        "convexity_label": "strong_convexity",
                    },
                ],
            )
            _write_csv(
                output_root / "setup_log.csv",
                [
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": "2025-12-14T02:00:00",
                        "side": "long",
                        "setup_type": "structural_compounding",
                        "setup_class": "A",
                        "classification": "A",
                        "structure_score": 1.0,
                        "liquidity_score": 0.7,
                        "ema_score": 0.4,
                        "htf_confirmation_score": 0.6,
                        "volatility_score": 0.5,
                        "risk_reward_score": 1.1,
                        "score": 4.1,
                        "total_score": 4.1,
                        "accepted": True,
                        "decision": "opened",
                        "entry_reason": "A setup: sweep_low near support with RR 3.0 and HTF bias bullish.",
                        "explanation": "long reclaim",
                        "pattern": "sweep_low",
                        "htf_aligned": True,
                        "risk_multiplier": 1.1,
                        "convexity_label": "strong_convexity",
                        "execution_timeframe": "1h",
                    },
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": "2026-03-01T02:00:00",
                        "side": "short",
                        "setup_type": "structural_compounding",
                        "setup_class": "A",
                        "classification": "A",
                        "structure_score": 1.0,
                        "liquidity_score": 0.8,
                        "ema_score": 0.5,
                        "htf_confirmation_score": 0.6,
                        "volatility_score": 0.5,
                        "risk_reward_score": 1.2,
                        "score": 4.5,
                        "total_score": 4.5,
                        "accepted": True,
                        "decision": "opened",
                        "entry_reason": "A setup: sweep_high near resistance with RR 9.0 and HTF bias bearish.",
                        "explanation": "short rejection",
                        "pattern": "sweep_high",
                        "htf_aligned": True,
                        "risk_multiplier": 1.15,
                        "convexity_label": "elite_convexity",
                        "execution_timeframe": "1h",
                    },
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": "2026-06-12T02:00:00",
                        "side": "short",
                        "setup_type": "structural_compounding",
                        "setup_class": "A",
                        "classification": "A",
                        "structure_score": 1.0,
                        "liquidity_score": 0.8,
                        "ema_score": 0.5,
                        "htf_confirmation_score": 0.6,
                        "volatility_score": 0.5,
                        "risk_reward_score": 1.2,
                        "score": 4.0,
                        "total_score": 4.0,
                        "accepted": True,
                        "decision": "opened",
                        "entry_reason": "A setup: sweep_high near resistance with RR 3.0 and HTF bias bearish.",
                        "explanation": "short rejection",
                        "pattern": "sweep_high",
                        "htf_aligned": True,
                        "risk_multiplier": 1.05,
                        "convexity_label": "strong_convexity",
                        "execution_timeframe": "1h",
                    },
                ],
            )
            _write_csv(output_root / "equity.csv", [{"timestamp": "2026-06-13T00:00:00", "equity": 26000}])
            _write_csv(
                output_root / "level_log.csv",
                [
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": "2025-12-13T00:00:00",
                        "price": 99.0,
                        "type": "support",
                        "timeframe_source": "1h",
                        "touch_count": 3,
                        "strength": 1.2,
                        "first_seen": "2025-12-13T00:00:00",
                        "last_touched": "2025-12-13T00:00:00",
                    },
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": "2025-12-13T00:00:00",
                        "price": 101.0,
                        "type": "resistance",
                        "timeframe_source": "1h",
                        "touch_count": 3,
                        "strength": 1.2,
                        "first_seen": "2025-12-13T00:00:00",
                        "last_touched": "2025-12-13T00:00:00",
                    },
                ],
            )
            _write_csv(
                output_root / "liquidity_events.csv",
                [
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": "2025-12-13T23:00:00",
                        "price": 101.0,
                        "type": "failed_breakout",
                        "side_implication": "short",
                        "source_timeframe": "1h",
                        "confidence": 0.7,
                    }
                ],
            )
            _write_csv(output_root / "cooldown_log.csv", [{"symbol": "BTCUSDT", "timestamp": "2026-06-01T00:00:00", "event_type": "cooldown_start", "reason": "danger"}])
            _write_csv(output_root / "pyramiding_log.csv", [{"symbol": "BTCUSDT", "timestamp": "2026-03-02T02:00:00", "event_type": "profit_lock", "reason": "danger"}])
            (output_root / "profit_vault.json").write_text(
                json.dumps({"base_capital": 20000, "active_trading_capital": 21000, "locked_profit": 5000}),
                encoding="utf-8",
            )
            (output_root / "summary.json").write_text(
                json.dumps(
                    {
                        "symbol": "BTCUSDT",
                        "execution_timeframe": "1h",
                        "trade_count": 3,
                        "setup_count": 3,
                        "level_count": 2,
                        "liquidity_event_count": 1,
                        "replay_checkpoint_timestamp": "2026-06-13T00:00:00",
                    }
                ),
                encoding="utf-8",
            )
            (output_root / "btcusdt_6m_1m_2025-12-13_to_2026-06-13.csv").write_text(
                "timestamp,open,high,low,close,volume\n2025-12-13T00:00:00,1,1,1,1,1\n",
                encoding="utf-8",
            )

            long_short_root = output_root / "long_short_edge_repair_audit_001" / "diagnostics"
            long_short_root.mkdir(parents=True, exist_ok=True)
            (output_root / "long_short_edge_repair_audit_001" / "long_short_edge_repair_summary.json").write_text(
                json.dumps({"recommended_next_research_patch": "PRESERVE_SHORTS_AND_DISABLE_BAD_LONG_ARCHETYPES"}),
                encoding="utf-8",
            )
            (long_short_root / "edge_repair_recommendation.json").write_text(
                json.dumps({"recommended_next_research_patch": "PRESERVE_SHORTS_AND_DISABLE_BAD_LONG_ARCHETYPES"}),
                encoding="utf-8",
            )
            _write_csv(long_short_root / "archetype_expectancy_breakdown.csv", [{"side": "short", "trade_count": 2, "total_R": 10.0}])

            long_damage_root = output_root / "long_damage_control_patch_audit_001" / "diagnostics"
            long_damage_root.mkdir(parents=True, exist_ok=True)
            (output_root / "long_damage_control_patch_audit_001" / "long_damage_control_patch_summary.json").write_text(
                json.dumps(
                    {
                        "best_patch_candidate": "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT",
                        "recommended_research_only_patch": "PRESERVE_PROVEN_SHORTS_ONLY",
                        "best_patch_ending_capital": 99334.11,
                        "best_patch_profit_factor": 3.81,
                        "best_patch_max_drawdown_pct": 0.0471,
                        "moonshot_dependency_after_patch": "HEALTHY_MOONSHOT_SUPPORT",
                    }
                ),
                encoding="utf-8",
            )
            (long_damage_root / "best_patch_candidate.json").write_text(
                json.dumps({"variant_name": "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT"}),
                encoding="utf-8",
            )
            _write_csv(
                long_damage_root / "patch_variant_summary.csv",
                [
                    {
                        "variant_name": "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT",
                        "ending_capital": 99334.11,
                        "profit_factor": 3.81,
                        "max_drawdown_pct": 0.0471,
                        "total_R": 166.43,
                    }
                ],
            )

            frozen_validation_root = output_root / "frozen_patch_validation_audit_001" / "diagnostics"
            frozen_validation_root.mkdir(parents=True, exist_ok=True)
            (output_root / "frozen_patch_validation_audit_001" / "status.json").write_text(
                json.dumps({"state": "complete", "real_money_allowed": False}),
                encoding="utf-8",
            )
            (output_root / "frozen_patch_validation_audit_001" / "frozen_patch_validation_summary.json").write_text(
                json.dumps(
                    {
                        "frozen_patch_candidate": "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT",
                        "retrospective_validation_only": True,
                        "true_unseen_proof_available": False,
                        "available_years": [2025, 2026],
                        "validation_window_count": 3,
                        "promotion_gate_classification": "READY_FOR_SMALL_CAPITAL_TRIAL_RESEARCH_ONLY",
                        "moonshot_dependency_in_validation": "HEALTHY_MOONSHOT_SUPPORT",
                    }
                ),
                encoding="utf-8",
            )
            (frozen_validation_root / "frozen_patch_rules.json").write_text(
                json.dumps({"frozen_patch_candidate": "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT"}),
                encoding="utf-8",
            )
            _write_csv(
                frozen_validation_root / "year_by_year_validation.csv",
                [
                    {"window_name": "2018", "trade_count": 0, "validation_label": "INSUFFICIENT_DATA"},
                    {"window_name": "2025", "trade_count": 1, "validation_label": "PASS_STRONG"},
                    {"window_name": "2026", "trade_count": 2, "validation_label": "PASS_STRONG"},
                ],
            )
            _write_csv(
                frozen_validation_root / "validation_window_summary.csv",
                [
                    {"window_name": "FULL_AVAILABLE_HISTORY_FROZEN_PATCH", "trade_count": 3, "total_R": 12.0, "profit_factor": 3.0, "ending_capital_from_20000": 26000},
                    {"window_name": "RECENT_12M_RETROSPECTIVE", "trade_count": 3, "total_R": 12.0, "profit_factor": 3.0, "ending_capital_from_20000": 26000},
                    {"window_name": "RECENT_6M_RETROSPECTIVE", "trade_count": 3, "total_R": 12.0, "profit_factor": 3.0, "ending_capital_from_20000": 26000},
                ],
            )
            _write_csv(
                frozen_validation_root / "walk_forward_validation.csv",
                [
                    {
                        "train_start": "2025-12-01",
                        "train_end": "2026-05-31",
                        "test_start": "2026-06-01",
                        "test_end": "2026-06-13",
                        "test_trade_count": 1,
                        "test_total_R": 2.0,
                        "test_profit_factor": 2.0,
                        "test_validation_label": "FAIL_TOO_FEW_TRADES",
                        "frozen_rules_applied_unchanged": True,
                    }
                ],
            )
            (frozen_validation_root / "promotion_gate_report.json").write_text(
                json.dumps({"classification": "READY_FOR_SMALL_CAPITAL_TRIAL_RESEARCH_ONLY", "true_unseen_proof_available": False}),
                encoding="utf-8",
            )

            broad_source = root / "data_storage" / "BTCUSDT" / "1m"
            broad_source.mkdir(parents=True, exist_ok=True)
            (broad_source / "BTCUSDT_1m_2018-01-01_to_2026-06-13.csv").write_text(
                "timestamp,open,high,low,close,volume\n2018-01-01T00:00:00,1,1,1,1,1\n",
                encoding="utf-8",
            )

            result = write_frozen_patch_forensic_integrity_audit(
                FrozenPatchForensicIntegrityAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "frozen_patch_forensic_integrity_audit_001",
                )
            )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            lineage = json.loads((output_root / "frozen_patch_forensic_integrity_audit_001" / "diagnostics" / "artifact_lineage_report.json").read_text(encoding="utf-8"))
            coverage = json.loads((output_root / "frozen_patch_forensic_integrity_audit_001" / "diagnostics" / "data_coverage_report.json").read_text(encoding="utf-8"))
            sample_reuse = json.loads((output_root / "frozen_patch_forensic_integrity_audit_001" / "diagnostics" / "sample_reuse_report.json").read_text(encoding="utf-8"))
            leakage = json.loads((output_root / "frozen_patch_forensic_integrity_audit_001" / "diagnostics" / "leakage_risk_report.json").read_text(encoding="utf-8"))
            rule_origin = json.loads((output_root / "frozen_patch_forensic_integrity_audit_001" / "diagnostics" / "frozen_rule_origin_report.json").read_text(encoding="utf-8"))
            validation_gap = json.loads((output_root / "frozen_patch_forensic_integrity_audit_001" / "diagnostics" / "validation_gap_report.json").read_text(encoding="utf-8"))
            replay_plan = json.loads((output_root / "frozen_patch_forensic_integrity_audit_001" / "diagnostics" / "required_next_replay_plan.json").read_text(encoding="utf-8"))

            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertEqual([2025, 2026], summary["available_trade_years"])
            self.assertFalse(summary["true_unseen_proof_available"])
            self.assertTrue(summary["current_validation_reused_discovery_sample"])
            self.assertEqual("HIGH", summary["sample_reuse_risk"])
            self.assertEqual("HIGH", summary["leakage_overfit_risk"])
            self.assertTrue(lineage["same_trade_artifact_used_for_discovery_and_validation"])
            self.assertFalse(lineage["truly_unseen_trade_sequence_used"])
            self.assertEqual("2025-12-14T02:00:00", coverage["available_trade_start"])
            self.assertEqual("2026-06-13T00:00:00", coverage["available_trade_end"])
            self.assertTrue(coverage["raw_source_history_sufficient_to_regenerate"])
            self.assertFalse(coverage["coverage_is_sufficient_for_multi_year_validation"])
            self.assertTrue(sample_reuse["current_validation_is_retrospective_only"])
            self.assertFalse(sample_reuse["walk_forward_result_used_genuinely_unseen_trade_windows"])
            self.assertEqual("HIGH", leakage["risk_level"])
            self.assertEqual("BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT", rule_origin["selected_variant"])
            self.assertTrue(rule_origin["was_rule_selected_using_current_sample"])
            self.assertFalse(rule_origin["can_rule_be_applied_without_current_sample_statistics"])
            self.assertIn("RETROSPECTIVE_PATCH_VALIDATION", validation_gap["current_proof_status"])
            self.assertIn("stage_1_generate_broad_historical_structural_outputs", replay_plan)

    def test_empty_state_is_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / "structural_compounding_lab"
            output_root = package_root / "output"
            output_root.mkdir(parents=True, exist_ok=True)

            result = write_frozen_patch_forensic_integrity_audit(
                FrozenPatchForensicIntegrityAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "frozen_patch_forensic_integrity_audit_001",
                )
            )

            status = json.loads(result["status"].read_text(encoding="utf-8"))
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("empty", status["state"])
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertFalse(summary["true_unseen_proof_available"])


if __name__ == "__main__":
    unittest.main()
