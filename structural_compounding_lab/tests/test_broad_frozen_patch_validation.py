import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from structural_compounding_lab.diagnostics.broad_frozen_patch_validation import (
    BroadFrozenPatchValidationConfig,
    write_broad_frozen_patch_validation,
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


def _build_trade_fixture() -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    trades: list[dict[str, object]] = []
    setups: list[dict[str, object]] = []
    levels: list[dict[str, object]] = []
    liquidity: list[dict[str, object]] = []
    base_time = datetime(2021, 1, 1, 0, 0, tzinfo=timezone.utc)

    def add_level(timestamp: datetime, price: float, level_type: str) -> None:
        levels.append(
            {
                "symbol": "BTCUSDT",
                "price": price,
                "type": level_type,
                "timeframe_source": "1h",
                "touch_count": 3,
                "recency": 0.0,
                "strength": 1.4,
                "first_seen": (timestamp - timedelta(hours=1)).isoformat(),
                "last_touched": timestamp.isoformat(),
                "display_only": True,
                "research_flag": True,
                "no_future_data": True,
                "timestamp": timestamp.isoformat(),
            }
        )

    def add_liquidity(timestamp: datetime, event_type: str, side_implication: str) -> None:
        liquidity.append(
            {
                "symbol": "BTCUSDT",
                "timestamp": timestamp.isoformat(),
                "price": 101.0,
                "type": event_type,
                "side_implication": side_implication,
                "source_timeframe": "1h",
                "confidence": 0.8,
                "no_future_data": True,
            }
        )

    def add_trade(
        *,
        trade_id: str,
        side: str,
        offset_days: int,
        r_multiple: float,
        pattern: str,
        context: str,
        personality_label: str,
        setup_class: str,
        htf_aligned: bool,
        ema_score: float,
        stop_distance: float,
        holding_bars: int,
        liquidity_type: str,
        exit_reason: str,
    ) -> None:
        entry_dt = base_time + timedelta(days=offset_days)
        exit_dt = entry_dt + timedelta(hours=max(1, min(holding_bars, 12)))
        entry_price = 100.0
        if side == "long":
            initial_stop = entry_price * (1.0 - stop_distance)
            exit_price = entry_price + (r_multiple * (entry_price - initial_stop))
        else:
            initial_stop = entry_price * (1.0 + stop_distance)
            exit_price = entry_price - (r_multiple * (initial_stop - entry_price))

        add_level(entry_dt - timedelta(minutes=30), 99.0 if context == "support" else 101.0, context)
        add_liquidity(entry_dt - timedelta(minutes=20), liquidity_type, side)

        trades.append(
            {
                "trade_id": trade_id,
                "symbol": "BTCUSDT",
                "side": side,
                "entry_time": entry_dt.isoformat(),
                "exit_time": exit_dt.isoformat(),
                "entry_price": entry_price,
                "exit_price": round(exit_price, 4),
                "initial_stop": round(initial_stop, 4),
                "trail_stop": round(initial_stop, 4),
                "pnl": round(r_multiple * 100.0, 4),
                "r_multiple": round(r_multiple, 4),
                "entry_reason": f"{setup_class} structural setup: {pattern} near {context} | RR {abs(r_multiple) + 2.0:.2f} | HTF {'aligned' if htf_aligned else 'counter'}",
                "exit_reason": exit_reason,
                "add_on_count": 0,
                "holding_bars": holding_bars,
                "setup_class": setup_class,
                "strategy_type": "structural_compounding",
                "moonshot_state": "moonshot" if r_multiple >= 5.0 else "normal",
                "entry_score": 4.25 if r_multiple > 0 else 3.4,
                "risk_multiplier": 1.0,
                "convexity_label": "elite_convexity" if "elite" in personality_label else "strong_convexity",
                "cooldown_fast_clear_eligible": "False",
                "personality_label": personality_label,
                "personality_confidence": 0.6,
                "pullback_type": "HEALTHY_CONTINUATION_PULLBACK",
                "pullback_quality_score": 0.5,
                "pullback_entry_price": entry_price,
                "pullback_stop_price": round(initial_stop, 4),
                "pullback_r_improvement": 1.0,
                "compounding_readiness_score": 0.4,
                "runner_label": "normal",
                "add_on_research_candidate": "False",
                "patience_score": 0.0,
                "de_risk_score": 0.5,
                "equity_after": 20000 + offset_days,
                "cycle_id": f"cycle-{offset_days // 180}",
            }
        )
        setups.append(
            {
                "symbol": "BTCUSDT",
                "timestamp": entry_dt.isoformat(),
                "side": side,
                "setup_type": "structural_compounding",
                "setup_class": setup_class,
                "classification": setup_class,
                "structure_score": 1.2,
                "liquidity_score": 0.8,
                "ema_score": ema_score,
                "htf_confirmation_score": 0.6 if htf_aligned else 0.0,
                "volatility_score": 0.5,
                "risk_reward_score": 1.1,
                "score": 4.2 if r_multiple > 0 else 3.2,
                "total_score": 4.2 if r_multiple > 0 else 3.2,
                "accepted": True,
                "decision": "opened",
                "entry_reason": f"{setup_class} structural setup: {pattern} near {context}",
                "explanation": f"{setup_class} structural setup: {pattern} near {context}",
                "pattern": pattern,
                "htf_aligned": htf_aligned,
                "risk_multiplier": 1.0,
                "convexity_label": "elite_convexity" if "elite" in personality_label else "strong_convexity",
                "cooldown_fast_clear_eligible": False,
                "execution_timeframe": "1h",
            }
        )

    for index in range(12):
        add_trade(
            trade_id=f"LB{index+1}",
            side="long",
            offset_days=index * 20,
            r_multiple=-1.0,
            pattern="sweep_low",
            context="support",
            personality_label="strong_convexity",
            setup_class="B",
            htf_aligned=False,
            ema_score=0.0,
            stop_distance=0.003,
            holding_bars=1,
            liquidity_type="failed_breakdown",
            exit_reason="stop_hit",
        )

    for index in range(12):
        add_trade(
            trade_id=f"LG{index+1}",
            side="long",
            offset_days=320 + (index * 20),
            r_multiple=1.2 if index < 10 else 5.5,
            pattern="sweep_low",
            context="support",
            personality_label="strong_convexity",
            setup_class="A",
            htf_aligned=True,
            ema_score=0.5,
            stop_distance=0.01,
            holding_bars=4,
            liquidity_type="failed_breakdown",
            exit_reason="target_hit",
        )

    for index in range(24):
        add_trade(
            trade_id=f"SG{index+1}",
            side="short",
            offset_days=640 + (index * 18),
            r_multiple=1.4 if index < 21 else 6.0,
            pattern="sweep_high",
            context="resistance",
            personality_label="elite_convexity",
            setup_class="A",
            htf_aligned=True,
            ema_score=0.5,
            stop_distance=0.01,
            holding_bars=3,
            liquidity_type="equal_highs",
            exit_reason="target_hit" if index < 21 else "moonshot_capture",
        )

    return trades, setups, levels, liquidity


class BroadFrozenPatchValidationTests(unittest.TestCase):
    def test_broad_frozen_patch_validation_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / "structural_compounding_lab"
            output_root = package_root / "output"
            broad_root = output_root / "broad_historical_structural_replay_001"
            broad_ledger_root = broad_root / "ledger"
            broad_diag_root = broad_root / "diagnostics"
            broad_report_root = broad_root / "reports"
            frozen_root = output_root / "frozen_patch_validation_audit_001" / "diagnostics"
            broad_diag_root.mkdir(parents=True, exist_ok=True)
            broad_report_root.mkdir(parents=True, exist_ok=True)
            frozen_root.mkdir(parents=True, exist_ok=True)

            trades, setups, levels, liquidity = _build_trade_fixture()
            _write_csv(broad_ledger_root / "trades.csv", trades)
            _write_csv(broad_ledger_root / "setup_log.csv", setups)
            _write_csv(broad_ledger_root / "level_log.csv", levels)
            _write_csv(broad_ledger_root / "liquidity_events.csv", liquidity)
            _write_csv(
                broad_ledger_root / "cooldown_log.csv",
                [{"symbol": "BTCUSDT", "timestamp": "2023-01-01T00:00:00+00:00", "reason": "danger_sniffed", "cooldown_bars": 4, "minimum_bars": 2, "event_type": "cooldown_start"}],
            )
            _write_csv(
                broad_ledger_root / "pyramiding_log.csv",
                [{"symbol": "BTCUSDT", "timestamp": "2024-01-01T00:00:00+00:00", "event_type": "profit_lock", "locked_profit": 600.0, "active_trading_capital": 20000.0, "convexity_label": "elite_convexity"}],
            )
            _write_csv(
                broad_ledger_root / "equity.csv",
                [{"timestamp": "2021-01-01T00:00:00+00:00", "equity": 20000.0}, {"timestamp": "2024-01-01T00:00:00+00:00", "equity": 26000.0}],
            )
            (broad_ledger_root / "summary.json").write_text(
                json.dumps(
                    {
                        "ending_equity": 26000.0,
                        "current_equity": 26000.0,
                        "active_trading_capital": 21000.0,
                        "locked_profit": 5000.0,
                        "floating_profit": 0.0,
                        "trade_count": len(trades),
                        "profit_lock_count": 1,
                        "add_on_event_count": 0,
                        "cooldown_event_count": 1,
                        "metrics": {
                            "profit_factor": 1.18,
                            "avg_r": 0.11,
                            "max_drawdown_pct": 0.16,
                        },
                    }
                ),
                encoding="utf-8",
            )
            (broad_ledger_root / "profit_vault.json").write_text(
                json.dumps(
                    {
                        "base_capital": 20000.0,
                        "active_trading_capital": 21000.0,
                        "locked_profit": 5000.0,
                        "floating_profit": 0.0,
                        "current_compounding_cycle_id": "cycle-4",
                    }
                ),
                encoding="utf-8",
            )
            (broad_ledger_root / "execution_realism").mkdir(parents=True, exist_ok=True)
            (broad_ledger_root / "execution_realism" / "execution_cost_sensitivity.json").write_text(
                json.dumps(
                    {
                        "scenario_metrics": {
                            "low_cost": {"net_pnl_after_costs": -500.0, "profit_factor_after_costs": 0.9, "average_cost_per_trade": 10.0, "total_fees": 120.0, "total_estimated_slippage": 80.0},
                            "normal_cost": {"net_pnl_after_costs": -1600.0, "profit_factor_after_costs": 0.7, "average_cost_per_trade": 20.0, "total_fees": 200.0, "total_estimated_slippage": 140.0},
                            "high_cost": {"net_pnl_after_costs": -2600.0, "profit_factor_after_costs": 0.55, "average_cost_per_trade": 28.0, "total_fees": 260.0, "total_estimated_slippage": 180.0},
                            "stress_cost": {"net_pnl_after_costs": -3600.0, "profit_factor_after_costs": 0.42, "average_cost_per_trade": 35.0, "total_fees": 340.0, "total_estimated_slippage": 260.0},
                        }
                    }
                ),
                encoding="utf-8",
            )
            (broad_root / "status.json").write_text(json.dumps({"state": "complete", "real_money_allowed": False}), encoding="utf-8")
            (broad_root / "broad_historical_replay_summary.json").write_text(
                json.dumps(
                    {
                        "source_data_start": "2018-01-01T00:00:00",
                        "source_data_end": "2026-06-13T00:00:00",
                        "generated_ledger_start": "2021-01-01T00:00:00",
                        "generated_ledger_end": "2026-06-13T00:00:00",
                        "trade_count": len(trades),
                        "long_trade_count": 24,
                        "short_trade_count": 24,
                        "coverage_sufficient_for_frozen_patch_validation": True,
                        "next_required_step": "APPLY_FROZEN_PATCH_TO_BROAD_HISTORICAL_LEDGER",
                    }
                ),
                encoding="utf-8",
            )
            (broad_diag_root / "replay_health_report.json").write_text(
                json.dumps({"successful_replay": True, "safe_for_frozen_patch_validation": True}),
                encoding="utf-8",
            )
            (broad_diag_root / "no_future_leakage_checks.json").write_text(
                json.dumps({"counts": {"passed": 6, "failed": 0, "unknown": 1}}),
                encoding="utf-8",
            )
            (broad_diag_root / "source_data_coverage.json").write_text(
                json.dumps({"source_path": "data_storage/BTCUSDT/1m/mock.csv", "missing_timestamp_count": 0, "duplicate_timestamp_count": 0}),
                encoding="utf-8",
            )
            (broad_report_root / "next_research_recommendation.json").write_text(
                json.dumps({"next_step": "APPLY_FROZEN_PATCH_TO_BROAD_HISTORICAL_LEDGER"}),
                encoding="utf-8",
            )

            (frozen_root / "frozen_patch_rules.json").write_text(
                json.dumps(
                    {
                        "frozen_patch_candidate": "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT",
                        "source_recommendation": "PRESERVE_PROVEN_SHORTS_ONLY",
                        "disabled_long_failure_modes": [
                            "LONG_COST_DOMINATED",
                            "LONG_COUNTER_HTF",
                            "LONG_DANGER_TOO_HIGH",
                            "LONG_EMA_FAKEOUT",
                            "LONG_OVERHEAD_RESISTANCE_TOO_CLOSE",
                            "LONG_TINY_STOP_TRAP",
                            "LONG_VWAP_FAKEOUT",
                            "LONG_WEAK_RECLAIM",
                        ],
                        "short_bucket_rule": {
                            "trade_count_min": 20,
                            "total_R_gt": 0.0,
                            "profit_factor_gt": 1.1,
                            "avg_R_gt": 0.0,
                            "matched_archetype_keys": [
                                "short|sweep_high|elite_convexity|resistance|equal_highs"
                            ],
                        },
                        "frozen_without_retuning": True,
                    }
                ),
                encoding="utf-8",
            )

            result = write_broad_frozen_patch_validation(
                BroadFrozenPatchValidationConfig(
                    package_root=package_root,
                    output_root=output_root / "broad_frozen_patch_validation_001",
                )
            )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            raw_vs_patch = json.loads((output_root / "broad_frozen_patch_validation_001" / "diagnostics" / "raw_vs_frozen_patch_comparison.json").read_text(encoding="utf-8"))
            long_short = json.loads((output_root / "broad_frozen_patch_validation_001" / "diagnostics" / "long_short_raw_vs_patch.json").read_text(encoding="utf-8"))
            moonshot = json.loads((output_root / "broad_frozen_patch_validation_001" / "diagnostics" / "moonshot_dependency_broad_patch.json").read_text(encoding="utf-8"))
            execution = json.loads((output_root / "broad_frozen_patch_validation_001" / "diagnostics" / "execution_cost_sensitivity_broad_patch.json").read_text(encoding="utf-8"))

            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertFalse(summary["behavior_change_allowed"])
            self.assertIn(summary["final_patch_classification"], {"PATCH_REJECTED_BROAD_HISTORY", "PATCH_IMPROVES_BUT_NOT_COST_SURVIVABLE", "PATCH_IMPROVES_AND_REQUIRES_REPAIR", "PATCH_VALIDATED_FOR_NEXT_STRESS_STAGE", "PATCH_STRONG_BROAD_RESEARCH_CANDIDATE"})
            self.assertEqual("BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT", summary["frozen_patch_candidate"])
            self.assertIn("raw_broad_actual", raw_vs_patch)
            self.assertIn("patched_broad_proxy_replay", raw_vs_patch)
            self.assertIn("raw_longs_net_damaging", long_short)
            self.assertIn("patched", moonshot)
            self.assertIn("low_cost", execution["scenarios"])

            with (output_root / "broad_frozen_patch_validation_001" / "diagnostics" / "yearly_raw_vs_patch.csv").open("r", encoding="utf-8") as handle:
                year_rows = list(csv.DictReader(handle))
            self.assertTrue(any(row["year"] == "2021" for row in year_rows))

            with (output_root / "broad_frozen_patch_validation_001" / "diagnostics" / "archetype_raw_vs_patch.csv").open("r", encoding="utf-8") as handle:
                archetype_rows = list(csv.DictReader(handle))
            self.assertTrue(any(row["archetype_key"] == "short|sweep_high|elite_convexity|resistance|equal_highs" for row in archetype_rows))

            with (output_root / "broad_frozen_patch_validation_001" / "diagnostics" / "top_removed_winning_trades.csv").open("r", encoding="utf-8") as handle:
                removed_winning_rows = list(csv.DictReader(handle))
            self.assertIsInstance(removed_winning_rows, list)
            self.assertTrue(all(float(row["r_multiple"]) > 0.0 for row in removed_winning_rows))

            with (output_root / "broad_frozen_patch_validation_001" / "diagnostics" / "top_removed_losing_trades.csv").open("r", encoding="utf-8") as handle:
                removed_losing_rows = list(csv.DictReader(handle))
            self.assertTrue(removed_losing_rows)
            self.assertTrue(any(float(row["r_multiple"]) < 0.0 for row in removed_losing_rows))

    def test_missing_artifacts_create_safe_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / "structural_compounding_lab"
            output_root = package_root / "output"
            output_root.mkdir(parents=True, exist_ok=True)

            result = write_broad_frozen_patch_validation(
                BroadFrozenPatchValidationConfig(
                    package_root=package_root,
                    output_root=output_root / "broad_frozen_patch_validation_001",
                )
            )

            status = json.loads(result["status"].read_text(encoding="utf-8"))
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("empty", status["state"])
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])


if __name__ == "__main__":
    unittest.main()
