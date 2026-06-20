import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from structural_compounding_lab.diagnostics.frozen_patch_validation_audit import (
    FrozenPatchValidationAuditConfig,
    write_frozen_patch_validation_audit,
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
    start_time = datetime(2021, 1, 1, 0, 0, tzinfo=timezone.utc)

    def add_trade(
        *,
        trade_id: str,
        side: str,
        offset_days: int,
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
        entry_dt = start_time + timedelta(days=offset_days)
        exit_dt = entry_dt + timedelta(hours=min(holding_bars, 23))
        entry_price = 100.0
        if side == "long":
            initial_stop = entry_price * (1.0 - stop_distance)
            exit_price = entry_price + (r_multiple * (entry_price - initial_stop))
        else:
            initial_stop = entry_price * (1.0 + stop_distance)
            exit_price = entry_price - (r_multiple * (initial_stop - entry_price))
        entry_reason = f"{setup_class} setup: {pattern} near {context} with RR {abs(r_multiple) + 2.0:.1f} and HTF bias {'bullish' if side == 'long' else 'bearish'}."
        score = 4.3 if r_multiple > 0 else 3.5
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
                "equity_after": 20000 + (offset_days * 5),
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
        add_trade(
            trade_id=f"LB{index+1}",
            side="long",
            offset_days=index * 20,
            r_multiple=-1.0 if index < 18 else -0.5,
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

    for index in range(24):
        add_trade(
            trade_id=f"LG{index+1}",
            side="long",
            offset_days=500 + (index * 20),
            r_multiple=5.8 if index == 0 else (1.25 if index < 18 else -0.4),
            pattern="sweep_low",
            context="support",
            convexity="elite_convexity" if index == 0 else "strong_convexity",
            setup_class="A",
            htf_aligned=True,
            ema_score=0.4,
            stop_distance=0.01,
            holding_bars=4,
            moonshot_state="moonshot" if index == 0 else "normal",
            exit_reason="moonshot_capture" if index == 0 else "target_hit",
        )

    for index in range(36):
        if index in {0, 12, 24}:
            r_multiple = 6.5
            moonshot = "moonshot"
        elif index < 24:
            r_multiple = 1.6
            moonshot = "normal"
        else:
            r_multiple = -0.7
            moonshot = "normal"
        add_trade(
            trade_id=f"SG{index+1}",
            side="short",
            offset_days=980 + (index * 20),
            r_multiple=r_multiple,
            pattern="sweep_high",
            context="resistance",
            convexity="strong_convexity",
            setup_class="A",
            htf_aligned=True,
            ema_score=0.5,
            stop_distance=0.01,
            holding_bars=5,
            moonshot_state=moonshot,
            exit_reason="moonshot_capture" if moonshot == "moonshot" else "target_hit",
        )

    return trades, setups


class FrozenPatchValidationAuditTests(unittest.TestCase):
    def test_frozen_patch_validation_outputs_expected_artifacts(self) -> None:
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
                        "first_seen": "2020-12-31T00:00:00+00:00",
                        "last_touched": "2020-12-31T00:00:00+00:00",
                        "display_only": True,
                        "research_flag": True,
                        "no_future_data": True,
                        "timestamp": "2020-12-31T00:00:00+00:00",
                    },
                    {
                        "symbol": "BTCUSDT",
                        "price": 101.0,
                        "type": "resistance",
                        "timeframe_source": "1h",
                        "touch_count": 3,
                        "recency": 0.0,
                        "strength": 1.4,
                        "first_seen": "2020-12-31T00:00:00+00:00",
                        "last_touched": "2020-12-31T00:00:00+00:00",
                        "display_only": True,
                        "research_flag": True,
                        "no_future_data": True,
                        "timestamp": "2020-12-31T00:00:00+00:00",
                    },
                ],
            )
            _write_csv(
                output_root / "liquidity_events.csv",
                [
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": "2020-12-31T23:00:00+00:00",
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
                        "timestamp": "2023-09-01T05:00:00+00:00",
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
                        "locked_profit": 600.0,
                        "active_trading_capital": 20000.0,
                        "cycle_id": "cycle-4",
                        "timestamp": "2024-01-01T05:00:00+00:00",
                        "symbol": "BTCUSDT",
                        "convexity_label": "elite_convexity",
                        "r_multiple": 6.5,
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
                json.dumps({"base_capital": 20000, "active_trading_capital": 20000, "locked_profit": 600.0}),
                encoding="utf-8",
            )

            patch_root = output_root / "long_damage_control_patch_audit_001" / "diagnostics"
            patch_root.mkdir(parents=True, exist_ok=True)
            (output_root / "long_damage_control_patch_audit_001" / "long_damage_control_patch_summary.json").write_text(
                json.dumps(
                    {
                        "best_patch_candidate": "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT",
                        "recommended_research_only_patch": "PRESERVE_PROVEN_SHORTS_ONLY",
                    }
                ),
                encoding="utf-8",
            )
            (patch_root / "best_patch_candidate.json").write_text(
                json.dumps({"variant_name": "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT"}),
                encoding="utf-8",
            )
            _write_csv(patch_root / "patch_variant_trade_replay.csv", [{"variant_name": "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT", "trade_id": "SG1"}])
            _write_csv(patch_root / "patch_variant_summary.csv", [{"variant_name": "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT", "ending_capital": 50000}])

            (output_root / "five_year_compounding_audit_001").mkdir(parents=True, exist_ok=True)
            (output_root / "five_year_compounding_audit_001" / "five_year_compounding_summary.json").write_text(
                json.dumps({"compounding_readiness_classification": "READY_FOR_SMALL_COMPOUNDING"}),
                encoding="utf-8",
            )
            (output_root / "long_short_edge_repair_audit_001").mkdir(parents=True, exist_ok=True)
            (output_root / "long_short_edge_repair_audit_001" / "long_short_edge_repair_summary.json").write_text(
                json.dumps({"recommended_next_research_patch": "PRESERVE_SHORTS_AND_DISABLE_BAD_LONG_ARCHETYPES"}),
                encoding="utf-8",
            )
            (output_root / "daily_opportunity_definition_refinement_001").mkdir(parents=True, exist_ok=True)
            (output_root / "daily_opportunity_definition_refinement_001" / "definition_refinement_summary.json").write_text(
                json.dumps({"classification": "definition_refined_research_only"}),
                encoding="utf-8",
            )

            result = write_frozen_patch_validation_audit(
                FrozenPatchValidationAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "frozen_patch_validation_audit_001",
                )
            )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            gate = json.loads(
                (output_root / "frozen_patch_validation_audit_001" / "diagnostics" / "promotion_gate_report.json").read_text(
                    encoding="utf-8"
                )
            )
            rules = json.loads(
                (output_root / "frozen_patch_validation_audit_001" / "diagnostics" / "frozen_patch_rules.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT", rules["frozen_patch_candidate"])
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertGreater(summary["validation_window_count"], 0)
            self.assertIn(gate["classification"], {"REJECT_PATCH_OVERFIT", "KEEP_RESEARCH_ONLY", "PROMISING_NEEDS_WALK_FORWARD", "READY_FOR_EXTENDED_PAPER_TEST", "READY_FOR_SMALL_CAPITAL_TRIAL_RESEARCH_ONLY"})

            with (output_root / "frozen_patch_validation_audit_001" / "diagnostics" / "year_by_year_validation.csv").open(
                "r", encoding="utf-8"
            ) as handle:
                year_rows = list(csv.DictReader(handle))
            self.assertTrue(any(row["window_name"] == "2021" for row in year_rows))
            self.assertTrue(any(row["window_name"] == "2023" for row in year_rows))

            with (output_root / "frozen_patch_validation_audit_001" / "diagnostics" / "walk_forward_validation.csv").open(
                "r", encoding="utf-8"
            ) as handle:
                walk_rows = list(csv.DictReader(handle))
            self.assertTrue(walk_rows)

            with (output_root / "frozen_patch_validation_audit_001" / "diagnostics" / "validation_window_summary.csv").open(
                "r", encoding="utf-8"
            ) as handle:
                validation_rows = list(csv.DictReader(handle))
            self.assertTrue(any(row["window_name"] == "FULL_AVAILABLE_HISTORY_FROZEN_PATCH" for row in validation_rows))

            moonshot_validation = json.loads(
                (output_root / "frozen_patch_validation_audit_001" / "diagnostics" / "moonshot_dependency_validation.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn("FULL_AVAILABLE_HISTORY_FROZEN_PATCH", moonshot_validation)

    def test_empty_state_is_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / "structural_compounding_lab"
            output_root = package_root / "output"
            output_root.mkdir(parents=True, exist_ok=True)

            result = write_frozen_patch_validation_audit(
                FrozenPatchValidationAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "frozen_patch_validation_audit_001",
                )
            )

            status = json.loads(result["status"].read_text(encoding="utf-8"))
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("empty", status["state"])
            self.assertTrue(summary["research_only"])
            self.assertEqual("KEEP_RESEARCH_ONLY", summary["promotion_gate_classification"])


if __name__ == "__main__":
    unittest.main()
