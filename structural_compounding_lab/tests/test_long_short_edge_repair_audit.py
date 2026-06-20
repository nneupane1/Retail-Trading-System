import csv
import json
import tempfile
import unittest
from pathlib import Path

from structural_compounding_lab.diagnostics.long_short_edge_repair_audit import (
    LongShortEdgeRepairAuditConfig,
    write_long_short_edge_repair_audit,
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


class LongShortEdgeRepairAuditTests(unittest.TestCase):
    def test_audit_detects_negative_longs_positive_shorts_and_writes_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / "structural_compounding_lab"
            output_root = package_root / "output"
            output_root.mkdir(parents=True, exist_ok=True)

            _write_csv(
                output_root / "trades.csv",
                [
                    {
                        "trade_id": "L1",
                        "symbol": "BTCUSDT",
                        "side": "long",
                        "entry_time": "2026-01-01T00:00:00+00:00",
                        "exit_time": "2026-01-01T01:00:00+00:00",
                        "entry_price": 100,
                        "exit_price": 99,
                        "initial_stop": 99.7,
                        "trail_stop": 99.7,
                        "pnl": -100,
                        "r_multiple": -1.0,
                        "entry_reason": "A setup: sweep_low near resistance with RR 2.5 and HTF bias neutral.",
                        "exit_reason": "stop_hit",
                        "add_on_count": 0,
                        "holding_bars": 1,
                        "setup_class": "A",
                        "strategy_type": "structural_compounding",
                        "moonshot_state": "normal",
                        "entry_score": 3.9,
                        "risk_multiplier": 1.15,
                        "convexity_label": "elite_convexity",
                        "cooldown_fast_clear_eligible": "False",
                        "equity_after": 19900,
                        "cycle_id": "cycle-0",
                    },
                    {
                        "trade_id": "L2",
                        "symbol": "BTCUSDT",
                        "side": "long",
                        "entry_time": "2026-01-02T00:00:00+00:00",
                        "exit_time": "2026-01-02T01:00:00+00:00",
                        "entry_price": 100,
                        "exit_price": 100.1,
                        "initial_stop": 99.7,
                        "trail_stop": 99.7,
                        "pnl": 10,
                        "r_multiple": 0.1,
                        "entry_reason": "B setup: sweep_low near support with RR 4.0 and HTF bias neutral.",
                        "exit_reason": "danger_sniffed",
                        "add_on_count": 0,
                        "holding_bars": 1,
                        "setup_class": "B",
                        "strategy_type": "structural_compounding",
                        "moonshot_state": "normal",
                        "entry_score": 3.7,
                        "risk_multiplier": 1.05,
                        "convexity_label": "strong_convexity",
                        "cooldown_fast_clear_eligible": "False",
                        "equity_after": 19910,
                        "cycle_id": "cycle-0",
                    },
                    {
                        "trade_id": "S1",
                        "symbol": "BTCUSDT",
                        "side": "short",
                        "entry_time": "2026-01-03T00:00:00+00:00",
                        "exit_time": "2026-01-03T04:00:00+00:00",
                        "entry_price": 100,
                        "exit_price": 96,
                        "initial_stop": 101,
                        "trail_stop": 101,
                        "pnl": 300,
                        "r_multiple": 3.0,
                        "entry_reason": "A setup: sweep_high near resistance with RR 5.0 and HTF bias neutral.",
                        "exit_reason": "danger_sniffed",
                        "add_on_count": 0,
                        "holding_bars": 4,
                        "setup_class": "A",
                        "strategy_type": "structural_compounding",
                        "moonshot_state": "normal",
                        "entry_score": 4.1,
                        "risk_multiplier": 1.15,
                        "convexity_label": "strong_convexity",
                        "cooldown_fast_clear_eligible": "False",
                        "equity_after": 20210,
                        "cycle_id": "cycle-0",
                    },
                    {
                        "trade_id": "S2",
                        "symbol": "BTCUSDT",
                        "side": "short",
                        "entry_time": "2026-01-04T00:00:00+00:00",
                        "exit_time": "2026-01-04T05:00:00+00:00",
                        "entry_price": 100,
                        "exit_price": 90,
                        "initial_stop": 101,
                        "trail_stop": 101,
                        "pnl": 600,
                        "r_multiple": 6.0,
                        "entry_reason": "A setup: retest_after_breakdown near range_high with RR 9.0 and HTF bias neutral.",
                        "exit_reason": "moonshot_capture",
                        "add_on_count": 0,
                        "holding_bars": 5,
                        "setup_class": "A",
                        "strategy_type": "structural_compounding",
                        "moonshot_state": "moonshot",
                        "entry_score": 4.2,
                        "risk_multiplier": 1.15,
                        "convexity_label": "elite_convexity",
                        "cooldown_fast_clear_eligible": "False",
                        "equity_after": 20810,
                        "cycle_id": "cycle-1",
                    },
                ],
            )
            _write_csv(
                output_root / "setup_log.csv",
                [
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": "2026-01-01T00:00:00+00:00",
                        "side": "long",
                        "setup_type": "structural_compounding",
                        "setup_class": "A",
                        "classification": "A",
                        "structure_score": 1.2,
                        "liquidity_score": 0.7,
                        "ema_score": 0.0,
                        "htf_confirmation_score": 0.0,
                        "volatility_score": 0.45,
                        "risk_reward_score": 1.0,
                        "score": 3.9,
                        "total_score": 3.9,
                        "accepted": True,
                        "decision": "opened",
                        "entry_reason": "A setup: sweep_low near resistance with RR 2.5 and HTF bias neutral.",
                        "explanation": "A setup: sweep_low near resistance with RR 2.5 and HTF bias neutral.",
                        "pattern": "sweep_low",
                        "htf_aligned": False,
                        "risk_multiplier": 1.15,
                        "convexity_label": "elite_convexity",
                        "cooldown_fast_clear_eligible": False,
                        "execution_timeframe": "1h",
                    },
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": "2026-01-02T00:00:00+00:00",
                        "side": "long",
                        "setup_type": "structural_compounding",
                        "setup_class": "B",
                        "classification": "B",
                        "structure_score": 1.0,
                        "liquidity_score": 0.7,
                        "ema_score": 0.0,
                        "htf_confirmation_score": 0.0,
                        "volatility_score": 0.45,
                        "risk_reward_score": 1.0,
                        "score": 3.7,
                        "total_score": 3.7,
                        "accepted": True,
                        "decision": "opened",
                        "entry_reason": "B setup: sweep_low near support with RR 4.0 and HTF bias neutral.",
                        "explanation": "B setup: sweep_low near support with RR 4.0 and HTF bias neutral.",
                        "pattern": "sweep_low",
                        "htf_aligned": False,
                        "risk_multiplier": 1.05,
                        "convexity_label": "strong_convexity",
                        "cooldown_fast_clear_eligible": False,
                        "execution_timeframe": "1h",
                    },
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": "2026-01-03T00:00:00+00:00",
                        "side": "short",
                        "setup_type": "structural_compounding",
                        "setup_class": "A",
                        "classification": "A",
                        "structure_score": 1.2,
                        "liquidity_score": 0.7,
                        "ema_score": 0.5,
                        "htf_confirmation_score": 0.0,
                        "volatility_score": 0.45,
                        "risk_reward_score": 1.0,
                        "score": 4.1,
                        "total_score": 4.1,
                        "accepted": True,
                        "decision": "opened",
                        "entry_reason": "A setup: sweep_high near resistance with RR 5.0 and HTF bias neutral.",
                        "explanation": "A setup: sweep_high near resistance with RR 5.0 and HTF bias neutral.",
                        "pattern": "sweep_high",
                        "htf_aligned": False,
                        "risk_multiplier": 1.15,
                        "convexity_label": "strong_convexity",
                        "cooldown_fast_clear_eligible": False,
                        "execution_timeframe": "1h",
                    },
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": "2026-01-04T00:00:00+00:00",
                        "side": "short",
                        "setup_type": "structural_compounding",
                        "setup_class": "A",
                        "classification": "A",
                        "structure_score": 1.2,
                        "liquidity_score": 0.7,
                        "ema_score": 0.5,
                        "htf_confirmation_score": 0.0,
                        "volatility_score": 0.45,
                        "risk_reward_score": 1.0,
                        "score": 4.2,
                        "total_score": 4.2,
                        "accepted": True,
                        "decision": "opened",
                        "entry_reason": "A setup: retest_after_breakdown near range_high with RR 9.0 and HTF bias neutral.",
                        "explanation": "A setup: retest_after_breakdown near range_high with RR 9.0 and HTF bias neutral.",
                        "pattern": "retest_after_breakdown",
                        "htf_aligned": False,
                        "risk_multiplier": 1.15,
                        "convexity_label": "elite_convexity",
                        "cooldown_fast_clear_eligible": False,
                        "execution_timeframe": "1h",
                    },
                ],
            )
            _write_csv(
                output_root / "level_log.csv",
                [
                    {"symbol": "BTCUSDT", "price": 100.2, "type": "resistance", "timeframe_source": "1h", "touch_count": 2, "recency": 0.0, "strength": 1.2, "first_seen": "2025-12-31T00:00:00+00:00", "last_touched": "2025-12-31T00:00:00+00:00", "display_only": True, "research_flag": True, "no_future_data": True, "timestamp": "2025-12-31T00:00:00+00:00"},
                    {"symbol": "BTCUSDT", "price": 99.5, "type": "support", "timeframe_source": "1h", "touch_count": 2, "recency": 0.0, "strength": 1.2, "first_seen": "2025-12-31T00:00:00+00:00", "last_touched": "2025-12-31T00:00:00+00:00", "display_only": True, "research_flag": True, "no_future_data": True, "timestamp": "2025-12-31T00:00:00+00:00"},
                ],
            )
            _write_csv(
                output_root / "liquidity_events.csv",
                [
                    {"symbol": "BTCUSDT", "timestamp": "2025-12-31T23:00:00+00:00", "price": 100.1, "type": "failed_breakout", "side_implication": "short", "source_timeframe": "1h", "confidence": 0.7, "no_future_data": True},
                    {"symbol": "BTCUSDT", "timestamp": "2026-01-03T23:00:00+00:00", "price": 100.1, "type": "retest_after_breakdown", "side_implication": "short", "source_timeframe": "1h", "confidence": 0.7, "no_future_data": True},
                ],
            )
            _write_csv(output_root / "cooldown_log.csv", [{"symbol": "BTCUSDT", "timestamp": "2026-01-03T04:00:00+00:00", "reason": "danger_sniffed", "cooldown_bars": 4, "minimum_bars": 2, "event_type": "cooldown_start"}])
            _write_csv(output_root / "pyramiding_log.csv", [{"event_type": "profit_lock", "reason": "danger_sniffed", "locked_profit": 300.0, "active_trading_capital": 20000.0, "cycle_id": "cycle-1", "timestamp": "2026-01-04T05:00:00+00:00", "symbol": "BTCUSDT", "convexity_label": "elite_convexity", "r_multiple": 6.0, "add_type": "", "side": "", "quantity": "", "price": "", "risk_multiplier": "", "stop_upgrade_r": ""}])
            (output_root / "profit_vault.json").write_text(json.dumps({"base_capital": 20000, "active_trading_capital": 20000, "locked_profit": 300.0}), encoding="utf-8")
            (output_root / "five_year_compounding_audit_001" / "diagnostics").mkdir(parents=True, exist_ok=True)
            (output_root / "five_year_compounding_audit_001" / "five_year_compounding_summary.json").write_text(
                json.dumps({"compounding_readiness_classification": "READY_FOR_SMALL_COMPOUNDING", "moonshot_profit_contribution_pct": 1.2}),
                encoding="utf-8",
            )
            _write_csv(output_root / "five_year_compounding_audit_001" / "diagnostics" / "full_active_capital_trade_growth.csv", [{"trade_id": "L1", "risk_eur": 100, "trade_R": -1.0}])
            (output_root / "daily_opportunity_definition_refinement_001").mkdir(parents=True, exist_ok=True)
            (output_root / "daily_opportunity_definition_refinement_001" / "definition_refinement_summary.json").write_text(
                json.dumps({"classification": "continue_research"}),
                encoding="utf-8",
            )
            (output_root / "daily_structural_opportunity_001").mkdir(parents=True, exist_ok=True)
            (output_root / "daily_structural_opportunity_001" / "daily_structural_opportunity_summary.json").write_text(
                json.dumps({"classification": "continue_research"}),
                encoding="utf-8",
            )

            result = write_long_short_edge_repair_audit(
                LongShortEdgeRepairAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "long_short_edge_repair_audit_001",
                )
            )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            recommendation = json.loads(
                (output_root / "long_short_edge_repair_audit_001" / "diagnostics" / "edge_repair_recommendation.json").read_text(
                    encoding="utf-8"
                )
            )
            dependency = json.loads(
                (output_root / "long_short_edge_repair_audit_001" / "diagnostics" / "moonshot_dependency_report.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(2, summary["long_trade_count"])
            self.assertEqual(2, summary["short_trade_count"])
            self.assertLess(summary["long_total_R"], 0.0)
            self.assertGreater(summary["short_total_R"], 0.0)
            self.assertEqual("PRESERVE_SHORTS_AND_DISABLE_BAD_LONG_ARCHETYPES", summary["recommended_next_research_patch"])
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertEqual("PRESERVE_SHORTS_AND_DISABLE_BAD_LONG_ARCHETYPES", recommendation["recommended_next_research_patch"])
            self.assertEqual(1, dependency["moonshot_5R_plus_count"])
            self.assertGreater(dependency["net_profit_with_10R_plus_capped_to_5R"], 0.0)

            archetypes_path = output_root / "long_short_edge_repair_audit_001" / "diagnostics" / "archetype_expectancy_breakdown.csv"
            with archetypes_path.open("r", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            labels = {row["expectancy_label"] for row in rows}
            self.assertTrue(labels)
            self.assertTrue(any(label in labels for label in {"REQUIRES_MORE_SAMPLE", "MOONSHOT_DEPENDENT", "NO_EDGE", "KEEP_AND_PRESERVE"}))

    def test_empty_state_is_safe_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / "structural_compounding_lab"
            output_root = package_root / "output"
            output_root.mkdir(parents=True, exist_ok=True)

            result = write_long_short_edge_repair_audit(
                LongShortEdgeRepairAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "long_short_edge_repair_audit_001",
                )
            )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            status = json.loads(result["status"].read_text(encoding="utf-8"))
            self.assertEqual(0, summary["long_trade_count"])
            self.assertEqual(0, summary["short_trade_count"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertEqual("empty", status["state"])


if __name__ == "__main__":
    unittest.main()
