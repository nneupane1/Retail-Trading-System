import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from structural_compounding_lab.diagnostics.long_damage_control_patch_audit import (
    LongDamageControlPatchAuditConfig,
    write_long_damage_control_patch_audit,
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


def _build_trade_rows() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    trades: list[dict[str, object]] = []
    setups: list[dict[str, object]] = []
    start_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)

    def append_trade(
        *,
        trade_id: str,
        side: str,
        trade_offset_days: int,
        r_multiple: float,
        pattern: str,
        context: str,
        convexity: str,
        setup_class: str,
        htf_aligned: bool,
        ema_score: float,
        stop_distance: float,
        holding_bars: int,
        moonshot_state: str = "normal",
        exit_reason: str = "target_hit",
    ) -> None:
        entry_price = 100.0
        if side == "long":
            initial_stop = entry_price * (1.0 - stop_distance)
            exit_price = entry_price + (r_multiple * (entry_price - initial_stop))
        else:
            initial_stop = entry_price * (1.0 + stop_distance)
            exit_price = entry_price - (r_multiple * (initial_stop - entry_price))
        entry_dt = start_time + timedelta(days=trade_offset_days)
        exit_dt = entry_dt + timedelta(hours=min(holding_bars, 23))
        entry_time = entry_dt.isoformat()
        exit_time = exit_dt.isoformat()
        pnl = r_multiple * 100.0
        score = 4.25 if r_multiple > 0 else 3.65
        entry_reason = f"{setup_class} setup: {pattern} near {context} with RR {abs(r_multiple) + 2.0:.1f} and HTF bias {'bullish' if side == 'long' else 'bearish'}."
        trades.append(
            {
                "trade_id": trade_id,
                "symbol": "BTCUSDT",
                "side": side,
                "entry_time": entry_time,
                "exit_time": exit_time,
                "entry_price": entry_price,
                "exit_price": round(exit_price, 4),
                "initial_stop": round(initial_stop, 4),
                "trail_stop": round(initial_stop, 4),
                "pnl": round(pnl, 4),
                "r_multiple": round(r_multiple, 4),
                "entry_reason": entry_reason,
                "exit_reason": exit_reason,
                "add_on_count": 0,
                "holding_bars": holding_bars,
                "setup_class": setup_class,
                "strategy_type": "structural_compounding",
                "moonshot_state": moonshot_state,
                "entry_score": score,
                "risk_multiplier": 1.15 if setup_class == "A" else 1.0,
                "convexity_label": convexity,
                "cooldown_fast_clear_eligible": "False",
                "equity_after": 20000 + ((trade_offset_days + 1) * 25),
                "cycle_id": f"cycle-{trade_offset_days // 10}",
            }
        )
        setups.append(
            {
                "symbol": "BTCUSDT",
                "timestamp": entry_time,
                "side": side,
                "setup_type": "structural_compounding",
                "setup_class": setup_class,
                "classification": setup_class,
                "structure_score": 1.25,
                "liquidity_score": 0.7,
                "ema_score": ema_score,
                "htf_confirmation_score": 0.6 if htf_aligned else 0.0,
                "volatility_score": 0.52,
                "risk_reward_score": 1.15,
                "score": score,
                "total_score": score,
                "accepted": True,
                "decision": "opened",
                "entry_reason": entry_reason,
                "explanation": entry_reason,
                "pattern": pattern,
                "htf_aligned": htf_aligned,
                "risk_multiplier": 1.15 if setup_class == "A" else 1.0,
                "convexity_label": convexity,
                "cooldown_fast_clear_eligible": False,
                "execution_timeframe": "1h",
            }
        )

    for index in range(24):
        append_trade(
            trade_id=f"LB{index+1}",
            side="long",
            trade_offset_days=index,
            r_multiple=-1.0 if index < 20 else -0.5,
            pattern="sweep_low",
            context="support",
            convexity="strong_convexity",
            setup_class="B",
            htf_aligned=False,
            ema_score=0.0,
            stop_distance=0.003,
            holding_bars=1,
            exit_reason="stop_hit",
        )

    for index in range(22):
        append_trade(
            trade_id=f"LG{index+1}",
            side="long",
            trade_offset_days=24 + index,
            r_multiple=5.5 if index == 0 else (1.2 if index < 16 else -0.6),
            pattern="sweep_low",
            context="support",
            convexity="elite_convexity" if index == 0 else "strong_convexity",
            setup_class="A",
            htf_aligned=True,
            ema_score=0.45,
            stop_distance=0.01,
            holding_bars=4,
            moonshot_state="moonshot" if index == 0 else "normal",
            exit_reason="moonshot_capture" if index == 0 else "target_hit",
        )

    for index in range(24):
        if index == 0:
            r_multiple = 8.0
        elif index == 1:
            r_multiple = 6.0
        elif index < 16:
            r_multiple = 1.5
        else:
            r_multiple = -0.7
        append_trade(
            trade_id=f"SG{index+1}",
            side="short",
            trade_offset_days=46 + index,
            r_multiple=r_multiple,
            pattern="sweep_high",
            context="resistance",
            convexity="strong_convexity",
            setup_class="A",
            htf_aligned=True,
            ema_score=0.5,
            stop_distance=0.01,
            holding_bars=5,
            moonshot_state="moonshot" if r_multiple >= 5.0 else "normal",
            exit_reason="moonshot_capture" if r_multiple >= 5.0 else "target_hit",
        )

    return trades, setups


class LongDamageControlPatchAuditTests(unittest.TestCase):
    def test_patch_audit_produces_variants_and_selects_best_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / "structural_compounding_lab"
            output_root = package_root / "output"
            output_root.mkdir(parents=True, exist_ok=True)

            trades, setups = _build_trade_rows()
            _write_csv(output_root / "trades.csv", trades)
            _write_csv(output_root / "setup_log.csv", setups)
            _write_csv(
                output_root / "level_log.csv",
                [
                    {
                        "symbol": "BTCUSDT",
                        "price": 99.0,
                        "type": "support",
                        "timeframe_source": "1h",
                        "touch_count": 3,
                        "recency": 0.0,
                        "strength": 1.4,
                        "first_seen": "2025-12-31T00:00:00+00:00",
                        "last_touched": "2025-12-31T00:00:00+00:00",
                        "display_only": True,
                        "research_flag": True,
                        "no_future_data": True,
                        "timestamp": "2025-12-31T00:00:00+00:00",
                    },
                    {
                        "symbol": "BTCUSDT",
                        "price": 101.0,
                        "type": "resistance",
                        "timeframe_source": "1h",
                        "touch_count": 3,
                        "recency": 0.0,
                        "strength": 1.4,
                        "first_seen": "2025-12-31T00:00:00+00:00",
                        "last_touched": "2025-12-31T00:00:00+00:00",
                        "display_only": True,
                        "research_flag": True,
                        "no_future_data": True,
                        "timestamp": "2025-12-31T00:00:00+00:00",
                    },
                ],
            )
            _write_csv(
                output_root / "liquidity_events.csv",
                [
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": "2025-12-31T23:00:00+00:00",
                        "price": 101.0,
                        "type": "failed_breakout",
                        "side_implication": "short",
                        "source_timeframe": "1h",
                        "confidence": 0.7,
                        "no_future_data": True,
                    }
                ],
            )
            _write_csv(
                output_root / "cooldown_log.csv",
                [
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": "2026-02-10T05:00:00+00:00",
                        "reason": "danger_sniffed",
                        "cooldown_bars": 4,
                        "minimum_bars": 2,
                        "event_type": "cooldown_start",
                    }
                ],
            )
            _write_csv(
                output_root / "pyramiding_log.csv",
                [
                    {
                        "event_type": "profit_lock",
                        "reason": "danger_sniffed",
                        "locked_profit": 500.0,
                        "active_trading_capital": 20000.0,
                        "cycle_id": "cycle-1",
                        "timestamp": "2026-02-10T05:00:00+00:00",
                        "symbol": "BTCUSDT",
                        "convexity_label": "elite_convexity",
                        "r_multiple": 8.0,
                        "add_type": "",
                        "side": "",
                        "quantity": "",
                        "price": "",
                        "risk_multiplier": "",
                        "stop_upgrade_r": "",
                    }
                ],
            )
            (output_root / "profit_vault.json").write_text(
                json.dumps({"base_capital": 20000, "active_trading_capital": 20000, "locked_profit": 500.0}),
                encoding="utf-8",
            )
            (output_root / "five_year_compounding_audit_001" / "diagnostics").mkdir(parents=True, exist_ok=True)
            (output_root / "five_year_compounding_audit_001" / "five_year_compounding_summary.json").write_text(
                json.dumps({"compounding_readiness_classification": "READY_FOR_SMALL_COMPOUNDING", "moonshot_profit_contribution_pct": 0.44}),
                encoding="utf-8",
            )
            _write_csv(
                output_root / "five_year_compounding_audit_001" / "diagnostics" / "full_active_capital_trade_growth.csv",
                [{"trade_id": "LB1", "risk_eur": 100, "trade_R": -1.0}],
            )
            (output_root / "long_short_edge_repair_audit_001" / "diagnostics").mkdir(parents=True, exist_ok=True)
            (output_root / "long_short_edge_repair_audit_001" / "long_short_edge_repair_summary.json").write_text(
                json.dumps({"recommended_next_research_patch": "PRESERVE_SHORTS_AND_DISABLE_BAD_LONG_ARCHETYPES"}),
                encoding="utf-8",
            )
            _write_csv(
                output_root / "long_short_edge_repair_audit_001" / "diagnostics" / "archetype_expectancy_breakdown.csv",
                [{"side": "short", "trade_count": 24, "total_R": 20.8}],
            )
            _write_csv(
                output_root / "long_short_edge_repair_audit_001" / "diagnostics" / "long_failure_modes.csv",
                [{"failure_mode": "LONG_TINY_STOP_TRAP", "trade_count": 24, "total_R": -22.0}],
            )
            _write_csv(
                output_root / "long_short_edge_repair_audit_001" / "diagnostics" / "short_success_modes.csv",
                [{"success_mode": "SHORT_SWEEP_HIGH_REJECTION", "trade_count": 24, "total_R": 20.8}],
            )
            (output_root / "long_short_edge_repair_audit_001" / "diagnostics" / "moonshot_dependency_report.json").write_text(
                json.dumps({"moonshot_5R_plus_count": 3, "net_profit_without_moonshots": 1250.0}),
                encoding="utf-8",
            )
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

            result = write_long_damage_control_patch_audit(
                LongDamageControlPatchAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "long_damage_control_patch_audit_001",
                )
            )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            best_candidate = json.loads(
                (output_root / "long_damage_control_patch_audit_001" / "diagnostics" / "best_patch_candidate.json").read_text(
                    encoding="utf-8"
                )
            )
            recommendation = json.loads(
                (output_root / "long_damage_control_patch_audit_001" / "diagnostics" / "research_only_patch_recommendation.json").read_text(
                    encoding="utf-8"
                )
            )
            moonshot_dependency = json.loads(
                (output_root / "long_damage_control_patch_audit_001" / "diagnostics" / "moonshot_dependency_after_patch.json").read_text(
                    encoding="utf-8"
                )
            )

            with (output_root / "long_damage_control_patch_audit_001" / "diagnostics" / "patch_variant_summary.csv").open(
                "r", encoding="utf-8"
            ) as handle:
                variant_rows = list(csv.DictReader(handle))
            variant_names = {row["variant_name"] for row in variant_rows}
            self.assertIn("BASELINE_CURRENT_SEQUENCE", variant_names)
            self.assertIn("LONGS_DISABLED_ALL_SHORTS_KEPT", variant_names)
            self.assertIn("BAD_LONG_ARCHETYPES_DISABLED_ALL_SHORTS_KEPT", variant_names)
            self.assertIn("SHORTS_ONLY_PROVEN_BUCKETS", variant_names)
            self.assertIn("MOONSHOT_CAPPED_PATCH", variant_names)
            self.assertIn("MOONSHOT_REMOVED_PATCH", variant_names)
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertGreater(summary["best_patch_ending_capital"], summary["baseline_ending_capital"])
            self.assertGreater(summary["best_patch_profit_factor"], summary["baseline_profit_factor"])
            self.assertGreater(summary["best_patch_total_R"], summary["baseline_total_R"])
            self.assertGreater(summary["long_R_removed"], 0.0)
            self.assertGreater(summary["short_R_preserved"], 0.0)
            self.assertIn(
                best_candidate["variant_name"],
                {
                    "BAD_LONG_ARCHETYPES_DISABLED_ALL_SHORTS_KEPT",
                    "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT",
                    "SHORTS_ONLY_PROVEN_BUCKETS",
                },
            )
            self.assertIn(
                recommendation["recommended_research_only_patch"],
                {
                    "PRESERVE_SHORTS_DISABLE_BAD_LONG_ARCHETYPES",
                    "PRESERVE_PROVEN_SHORTS_ONLY",
                    "PRESERVE_SHORTS_DISABLE_ALL_LONGS",
                },
            )
            self.assertIn("BASELINE_CURRENT_SEQUENCE", moonshot_dependency)
            self.assertIn(best_candidate["variant_name"], moonshot_dependency)

            with (
                output_root / "long_damage_control_patch_audit_001" / "diagnostics" / "preserved_short_edge_impact.csv"
            ).open("r", encoding="utf-8") as handle:
                preserved_shorts = list(csv.DictReader(handle))
            self.assertTrue(any(row["short_success_mode"] == "SHORT_SWEEP_HIGH_REJECTION" for row in preserved_shorts))

            with (
                output_root / "long_damage_control_patch_audit_001" / "diagnostics" / "disabled_long_archetype_impact.csv"
            ).open("r", encoding="utf-8") as handle:
                disabled_longs = list(csv.DictReader(handle))
            self.assertTrue(any(row["archetype_or_failure_mode"] == "LONG_TINY_STOP_TRAP" for row in disabled_longs))

    def test_empty_state_outputs_are_safe_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / "structural_compounding_lab"
            output_root = package_root / "output"
            output_root.mkdir(parents=True, exist_ok=True)

            result = write_long_damage_control_patch_audit(
                LongDamageControlPatchAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "long_damage_control_patch_audit_001",
                )
            )

            status = json.loads(result["status"].read_text(encoding="utf-8"))
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("empty", status["state"])
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertEqual("NO_PATCH_EDGE_TOO_THIN", summary["recommended_research_only_patch"])


if __name__ == "__main__":
    unittest.main()
