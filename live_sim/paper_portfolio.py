"""Lean multi-asset live paper portfolio with adaptive score-based selection."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from common.debug import debug_print as print
from config import AppConfig
from entry.opportunity_ranking import OpportunityScorer, bucket_floor, clamp, score_bucket_label
from exit.exit_engine import ExitEngine
from position.sizing import PositionSizer
from simulation.account import Account
from simulation.trade import Trade
from sniffing.trend_sniffer import TrendSniffer


class LivePaperPortfolio:
    """Manages live paper positions across multiple symbols with shared equity."""

    def __init__(
        self,
        *,
        trade_logger=None,
        state_logger=None,
        signal_logger=None,
        scorer=None,
        account=None,
        position_sizer=None,
        exit_engine=None,
        trend_sniffer=None,
        config=None,
    ):
        self.config = config or AppConfig.load()
        getter = getattr(self.config, "get", None)
        raw = (
            getter("live_sim", "paper_portfolio", default={})
            if callable(getter)
            else {}
        ) or {}

        self.account = account or Account(config=self.config)
        self.trade_logger = trade_logger
        self.state_logger = state_logger
        self.signal_logger = signal_logger
        self.position_sizer = position_sizer or PositionSizer(config=self.config)
        self.exit_engine = exit_engine or ExitEngine()
        self.trend_sniffer = trend_sniffer or TrendSniffer(config=self.config)
        self.scorer = scorer or OpportunityScorer(config=self.config)
        ema_periods = self.config.require("features", "ema_periods")
        self.fast_ema_column = f"ema{ema_periods['fast']}"
        self.slow_ema_column = f"ema{ema_periods['slow']}"

        self.open_positions = []
        self.min_trades_per_day = int(raw.get("min_trades_per_day", 10))
        self.target_trades_per_day = int(raw.get("target_trades_per_day", 10))
        self.max_trades_per_day = int(raw.get("max_trades_per_day", 15))
        self.base_threshold = float(raw.get("base_threshold", 0.65))
        self.current_threshold = self.base_threshold
        self.min_threshold = float(raw.get("min_threshold", 0.50))
        self.max_threshold = float(raw.get("max_threshold", 0.90))
        self.pacing_relax_step = float(raw.get("pacing_relax_step", 0.05))
        self.pacing_tighten_step = float(raw.get("pacing_tighten_step", 0.03))
        self.threshold_smoothing = float(raw.get("threshold_smoothing", 0.20))
        self.min_profitable_bucket_count = int(raw.get("min_profitable_bucket_count", 30))
        self.recency_lookback_days = int(raw.get("recency_lookback_days", 60))
        self.recency_max_trades = int(raw.get("recency_max_trades", 300))
        self.recency_min_bucket_trades = int(raw.get("recency_min_bucket_trades", 50))
        self.recency_min_strategy_trades = int(raw.get("recency_min_strategy_trades", 30))
        self.health_reference_avg_r = float(raw.get("health_reference_avg_r", 0.02))
        self.strategy_health_profiles = dict(raw.get("strategy_health_profiles", {}) or {})
        self.strategy_bucket_health_profiles = dict(
            raw.get("strategy_bucket_health_profiles", {}) or {}
        )
        self.strategy_threshold_offsets = {
            str(strategy_type): float(value)
            for strategy_type, value in dict(raw.get("strategy_threshold_offsets", {}) or {}).items()
        }
        self.bucket_negative_risk_multiplier = float(
            raw.get("bucket_negative_risk_multiplier", 0.25)
        )
        self.bucket_positive_floor_multiplier = float(
            raw.get("bucket_positive_floor_multiplier", 0.60)
        )
        self.bucket_positive_cap = float(raw.get("bucket_positive_cap", 1.20))
        self.strategy_negative_risk_multiplier = float(
            raw.get("strategy_negative_risk_multiplier", 0.30)
        )
        self.strategy_positive_floor_multiplier = float(
            raw.get("strategy_positive_floor_multiplier", 0.75)
        )
        self.strategy_positive_cap = float(raw.get("strategy_positive_cap", 1.20))
        self.disable_non_core_negative_strategies = bool(
            raw.get("disable_non_core_negative_strategies", True)
        )
        self.strategy_emergency_disable_min_trades = int(
            raw.get("strategy_emergency_disable_min_trades", 8)
        )
        self.strategy_emergency_disable_avg_r = float(
            raw.get("strategy_emergency_disable_avg_r", -0.20)
        )
        self.performance_history_limit = int(raw.get("performance_history_limit", 5000))
        self.max_total_risk_fraction = float(raw.get("max_total_risk_fraction", 0.04))
        self.max_trades_per_asset = int(raw.get("max_trades_per_asset", 2))
        self.max_same_direction_positions = int(raw.get("max_same_direction_positions", 6))
        self.max_new_positions_per_step = int(raw.get("max_new_positions_per_step", 3))
        self.min_risk_per_trade = float(raw.get("min_risk_per_trade", 0.0025))
        self.max_risk_per_trade = float(raw.get("max_risk_per_trade", 0.0060))
        self.trailing_activation_r = float(raw.get("trailing_activation_r", 1.2))
        self.breakeven_trigger_r = float(raw.get("breakeven_trigger_r", 1.0))
        self.slow_grind_max_bars = int(raw.get("slow_grind_max_bars", 8))
        self.slow_grind_open_r_max = float(raw.get("slow_grind_open_r_max", 1.0))
        self.weight_update_min_trades = int(raw.get("weight_update_min_trades", 30))
        convexity = dict(raw.get("convexity", {}) or {})
        self.convexity_enabled = bool(convexity.get("enabled", False))
        self.convexity_strategy_types = {
            str(strategy_type or "core")
            for strategy_type in (convexity.get("strategy_types") or ["core"])
        }
        self.convexity_probe_fraction = float(convexity.get("probe_fraction", 0.35))
        self.convexity_min_score = float(convexity.get("min_score", 0.82))
        self.convexity_promote_trigger_r = float(convexity.get("promote_trigger_r", 0.60))
        self.convexity_promote_target_multiple = float(
            convexity.get("promote_target_multiple", 1.00)
        )
        self.convexity_add_trigger_r = float(convexity.get("add_trigger_r", 1.40))
        self.convexity_add_target_multiple = float(
            convexity.get("add_target_multiple", 1.25)
        )
        self.convexity_max_target_multiple = float(
            convexity.get("max_target_multiple", 1.25)
        )
        self.convexity_max_layers = int(convexity.get("max_layers", 3))
        self.convexity_min_body_strength = float(convexity.get("min_body_strength", 1.0))
        self.convexity_min_close_position = float(
            convexity.get("min_close_position", 0.60)
        )
        self.convexity_min_expansion = float(convexity.get("min_expansion", 1.0))
        self.convexity_add_min_body_strength = float(
            convexity.get("add_min_body_strength", 1.4)
        )
        self.convexity_add_min_close_position = float(
            convexity.get("add_min_close_position", 0.72)
        )
        self.convexity_add_min_expansion = float(
            convexity.get("add_min_expansion", 1.15)
        )
        self.convexity_max_abs_vwap_distance = float(
            convexity.get("max_abs_vwap_distance", 0.012)
        )
        self.convexity_min_bars_between_adds = int(
            convexity.get("min_bars_between_adds", 1)
        )
        self.convexity_use_active_stop_for_adds = bool(
            convexity.get("use_active_stop_for_adds", True)
        )
        self.convexity_add_min_stop_distance_r_multiple = float(
            convexity.get("add_min_stop_distance_r_multiple", 0.50)
        )
        self.convexity_hold_extension_bars = int(
            convexity.get("hold_extension_bars", 4)
        )
        raw_bucket_multipliers = dict(
            raw.get(
                "score_bucket_risk_multipliers",
                {
                    "0.9-1.0": 1.0,
                    "0.8-0.9": 0.35,
                    "0.7-0.8": 0.0,
                    "0.6-0.7": 0.0,
                    "<0.6": 0.0,
                },
            )
            or {}
        )
        self.score_bucket_risk_multipliers = {
            str(bucket): float(multiplier)
            for bucket, multiplier in raw_bucket_multipliers.items()
        }
        self.allowed_sides = {
            str(side).lower()
            for side in (raw.get("allowed_sides") or ["long"])
        }
        self.strategy_allowed_sides = {
            str(strategy_type): {
                str(side).lower()
                for side in (allowed_sides or [])
            }
            for strategy_type, allowed_sides in dict(
                raw.get("strategy_allowed_sides", {}) or {}
            ).items()
        }
        def _strategy_feature_enabled(strategy_type):
            strategy_type = str(strategy_type or "core")
            if strategy_type == "core":
                return True
            if not callable(getter):
                return False
            if strategy_type == "swing_moonshot":
                return bool(
                    getter("strategy", "moonshots", "swing", "enabled", default=False)
                )
            if strategy_type == "intraday_moonshot":
                return bool(
                    getter("strategy", "moonshots", "intraday", "enabled", default=False)
                )
            return bool(getter("strategy", strategy_type, "enabled", default=False))

        self.strategy_sleeves = {}
        for strategy_type, values in dict(raw.get("strategy_sleeves", {}) or {}).items():
            if not _strategy_feature_enabled(strategy_type):
                continue
            sleeve = dict(values or {})
            if not bool(sleeve.get("enabled", True)):
                continue
            self.strategy_sleeves[str(strategy_type)] = {
                "reserved_risk_fraction": max(
                    0.0,
                    float(sleeve.get("reserved_risk_fraction", 0.0) or 0.0),
                ),
                "max_new_positions_per_step": (
                    None
                    if sleeve.get("max_new_positions_per_step") in (None, "")
                    else int(sleeve.get("max_new_positions_per_step"))
                ),
                "block_if_symbol_has_other_strategy_position": bool(
                    sleeve.get("block_if_symbol_has_other_strategy_position", False)
                ),
                "ignore_global_step_cap": bool(
                    sleeve.get("ignore_global_step_cap", False)
                ),
            }
        self.total_reserved_sleeve_risk_fraction = sum(
            float(values.get("reserved_risk_fraction", 0.0) or 0.0)
            for values in self.strategy_sleeves.values()
        )
        self.shared_pool_risk_fraction_cap = max(
            0.0,
            self.max_total_risk_fraction - self.total_reserved_sleeve_risk_fraction,
        )
        allocator_v2 = dict(raw.get("allocator_v2", {}) or {})
        self.allocator_v2_enabled = bool(allocator_v2.get("enabled", False))
        leader_dominance = dict(allocator_v2.get("leader_dominance", {}) or {})
        self.allocator_v2_leader_enabled = bool(
            leader_dominance.get("enabled", True)
        )
        self.allocator_v2_leader_min_gap = float(
            leader_dominance.get("min_gap", 0.08)
        )
        self.allocator_v2_leader_boost = float(
            leader_dominance.get("boost", 0.25)
        )
        agreement_bonus = dict(allocator_v2.get("agreement_bonus", {}) or {})
        self.allocator_v2_agreement_enabled = bool(
            agreement_bonus.get("enabled", True)
        )
        concentration_brake = dict(allocator_v2.get("concentration_brake", {}) or {})
        self.allocator_v2_concentration_brake_enabled = bool(
            concentration_brake.get("enabled", False)
        )
        self.allocator_v2_brake_min_closed_trades = int(
            concentration_brake.get("min_closed_trades", 2) or 2
        )
        self.allocator_v2_brake_daily_loss_fraction_trigger = float(
            concentration_brake.get("daily_loss_fraction_trigger", 0.005) or 0.005
        )
        self.allocator_v2_brake_loss_streak_trigger = int(
            concentration_brake.get("loss_streak_trigger", 3) or 3
        )
        self.allocator_v2_brake_budget_multiplier = float(
            concentration_brake.get("budget_multiplier", 0.75) or 0.75
        )
        self.allocator_v2_brake_core_budget_multiplier = float(
            concentration_brake.get("core_budget_multiplier", 0.60) or 0.60
        )
        self.allocator_v2_brake_priority_multiplier = float(
            concentration_brake.get("priority_multiplier", 0.90) or 0.90
        )
        self.allocator_v2_brake_core_priority_multiplier = float(
            concentration_brake.get("core_priority_multiplier", 0.80) or 0.80
        )
        self.allocator_v2_brake_leader_boost_multiplier = float(
            concentration_brake.get("leader_boost_multiplier", 0.40) or 0.40
        )
        self.allocator_v2_brake_uniform_weight_blend = float(
            concentration_brake.get("uniform_weight_blend", 0.50) or 0.50
        )
        self.allocator_v2_agreement_pairs = []
        for values in list(agreement_bonus.get("pairs") or []):
            entry = dict(values or {})
            primary = str(entry.get("primary") or "").strip()
            secondary = str(entry.get("secondary") or "").strip()
            if not primary or not secondary:
                continue
            self.allocator_v2_agreement_pairs.append(
                {
                    "primary": primary,
                    "secondary": secondary,
                    "primary_bonus": float(entry.get("primary_bonus", 0.10) or 0.10),
                    "secondary_bonus": float(
                        entry.get("secondary_bonus", 0.0) or 0.0
                    ),
                }
            )
        cross_sleeve_coordination = dict(
            allocator_v2.get("cross_sleeve_coordination", {}) or {}
        )
        self.allocator_v2_cross_sleeve_enabled = bool(
            cross_sleeve_coordination.get("enabled", False)
        )
        self.allocator_v2_cross_sleeve_rules = {}
        for rule_name, values in dict(
            cross_sleeve_coordination.get("rules", {}) or {}
        ).items():
            entry = dict(values or {})
            self.allocator_v2_cross_sleeve_rules[str(rule_name)] = {
                "priority_multiplier": float(
                    entry.get("priority_multiplier", 1.0) or 1.0
                ),
                "base_risk_multiplier": float(
                    entry.get("base_risk_multiplier", 1.0) or 1.0
                ),
                "sleeve_cap_multiplier": float(
                    entry.get("sleeve_cap_multiplier", 1.0) or 1.0
                ),
            }
        self.allocator_v2_sleeves = {}
        for sleeve_name, values in dict(allocator_v2.get("sleeves", {}) or {}).items():
            sleeve = dict(values or {})
            rank_weights = []
            for value in list(sleeve.get("rank_weights") or [1.0]):
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    continue
                if numeric > 0.0:
                    rank_weights.append(numeric)
            if not rank_weights:
                rank_weights = [1.0]
            max_candidates = sleeve.get("max_candidates")
            self.allocator_v2_sleeves[str(sleeve_name)] = {
                "priority_multiplier": float(
                    sleeve.get("priority_multiplier", 1.0) or 1.0
                ),
                "rank_weights": rank_weights,
                "max_candidates": (
                    len(rank_weights)
                    if max_candidates in (None, "")
                    else max(1, int(max_candidates))
                ),
                "max_risk_fraction_multiplier": float(
                    sleeve.get("max_risk_fraction_multiplier", 1.0) or 1.0
                ),
                "absolute_max_risk_fraction": (
                    None
                    if sleeve.get("absolute_max_risk_fraction") in (None, "")
                    else float(sleeve.get("absolute_max_risk_fraction"))
                ),
            }

        self.current_trading_day = None
        self.day_start_equity = self.account.equity
        self.daily_entries_taken = 0
        self.daily_closed_trades = 0
        self.daily_closed_pnl = 0.0
        self.daily_loss_streak = 0
        self.daily_history = []

        self.score_stats = defaultdict(
            lambda: {"count": 0, "wins": 0, "total_R": 0.0, "total_pnl": 0.0}
        )
        self.strategy_stats = defaultdict(
            lambda: {"count": 0, "wins": 0, "total_R": 0.0, "total_pnl": 0.0}
        )
        self.feature_stats = defaultdict(
            lambda: {"sum_pos": 0.0, "sum_neg": 0.0}
        )
        self.performance_history = []
        self.selection_monitor_recent_limit = max(
            50,
            int(raw.get("selection_monitor_recent_limit", 500) or 500),
        )
        self.selection_reason_counts = defaultdict(int)
        self.selection_reason_counts_by_strategy = defaultdict(
            lambda: defaultdict(int)
        )
        self.selection_reason_history = []
        self.recent_score_stats = {}
        self.recent_score_trade_stats = {}
        self.recent_strategy_stats = {}
        self.recent_strategy_trade_stats = {}
        self.recent_strategy_bucket_stats = {}
        self.recent_strategy_bucket_trade_stats = {}
        self.runtime_policy_guards = {}
        if callable(getter):
            strategy_types = set(self.strategy_sleeves.keys())
            strategy_types.update(
                str(name)
                for name in dict(getter("strategy", default={}) or {}).keys()
            )
            for strategy_type in sorted(strategy_types):
                guard = dict(
                    getter(
                        "strategy",
                        strategy_type,
                        "runtime_policy_guard",
                        default={},
                    )
                    or {}
                )
                if guard:
                    self.runtime_policy_guards[str(strategy_type)] = guard
        self.current_threshold_floor = self.base_threshold
        self.current_threshold_source = "base"
        self.last_top_symbols = []

    @staticmethod
    def _selection_reason_cap_pressure_reasons():
        return {
            "allocator_zero_risk",
            "risk_cap",
            "shared_risk_cap",
            "strategy_sleeve_cap",
            "strategy_risk_cap",
        }

    def _trim_selection_reason_history(self):
        if self.selection_monitor_recent_limit <= 0:
            return
        if len(self.selection_reason_history) <= self.selection_monitor_recent_limit:
            return
        self.selection_reason_history = self.selection_reason_history[
            -self.selection_monitor_recent_limit :
        ]

    def _record_selection_decisions(self, states, final_reason_by_id, timestamp):
        timestamp_value = self._normalize_time_value(timestamp)
        for state in states:
            reason = str(final_reason_by_id.get(state["id"]) or "unknown")
            strategy_type = str(state.get("strategy_type") or "core")
            self.selection_reason_counts[reason] += 1
            self.selection_reason_counts_by_strategy[strategy_type][reason] += 1
            self.selection_reason_history.append(
                {
                    "timestamp": timestamp_value,
                    "strategy_type": strategy_type,
                    "selection_reason": reason,
                }
            )
        self._trim_selection_reason_history()

    def _selection_reason_summary_rows(self, counts):
        total = sum(int(value or 0) for value in counts.values())
        cap_reasons = self._selection_reason_cap_pressure_reasons()
        rows = []
        for reason, count in counts.items():
            rows.append(
                {
                    "selection_reason": str(reason),
                    "count": int(count or 0),
                    "share_of_decisions": (
                        float(count or 0) / float(total) if total > 0 else 0.0
                    ),
                    "is_cap_pressure": str(reason) in cap_reasons,
                }
            )
        rows.sort(
            key=lambda item: (-int(item["count"]), str(item["selection_reason"])),
        )
        return rows

    def _selection_reason_counts_for_recent_window(self):
        counts = defaultdict(int)
        counts_by_strategy = defaultdict(lambda: defaultdict(int))
        for record in self.selection_reason_history:
            reason = str(record.get("selection_reason") or "unknown")
            strategy_type = str(record.get("strategy_type") or "core")
            counts[reason] += 1
            counts_by_strategy[strategy_type][reason] += 1
        return counts, counts_by_strategy

    def _selection_reason_by_strategy_rows(self, counts_by_strategy):
        cap_reasons = self._selection_reason_cap_pressure_reasons()
        rows = []
        for strategy_type, reason_counts in counts_by_strategy.items():
            strategy_total = sum(int(value or 0) for value in reason_counts.values())
            for reason, count in reason_counts.items():
                rows.append(
                    {
                        "strategy_type": str(strategy_type),
                        "selection_reason": str(reason),
                        "count": int(count or 0),
                        "share_of_strategy_decisions": (
                            float(count or 0) / float(strategy_total)
                            if strategy_total > 0
                            else 0.0
                        ),
                        "is_cap_pressure": str(reason) in cap_reasons,
                    }
                )
        rows.sort(
            key=lambda item: (
                str(item["strategy_type"]),
                -int(item["count"]),
                str(item["selection_reason"]),
            )
        )
        return rows

    def _cap_pressure_summary_from_counts(self, counts):
        total = sum(int(value or 0) for value in counts.values())
        cap_reasons = self._selection_reason_cap_pressure_reasons()
        cap_counts = {
            reason: int(counts.get(reason, 0) or 0)
            for reason in sorted(cap_reasons)
        }
        opened_count = int(counts.get("opened", 0) or 0)
        cap_blocked_count = sum(cap_counts.values())
        rejected_count = max(0, total - opened_count)
        return {
            "total_decisions": total,
            "opened_count": opened_count,
            "rejected_count": rejected_count,
            "cap_blocked_count": cap_blocked_count,
            "cap_block_rate": (
                float(cap_blocked_count) / float(total) if total > 0 else 0.0
            ),
            "opened_share": (
                float(opened_count) / float(total) if total > 0 else 0.0
            ),
            "shared_risk_cap_count": cap_counts.get("shared_risk_cap", 0),
            "strategy_sleeve_cap_count": cap_counts.get("strategy_sleeve_cap", 0),
            "risk_cap_count": cap_counts.get("risk_cap", 0),
            "strategy_risk_cap_count": cap_counts.get("strategy_risk_cap", 0),
            "allocator_zero_risk_count": cap_counts.get("allocator_zero_risk", 0),
        }

    def _runtime_policy_states_snapshot(self):
        states = {}
        for strategy_type, guard in sorted(self.runtime_policy_guards.items()):
            states[str(strategy_type)] = self.strategy_runtime_policy_state(
                strategy_type,
                guard,
            )
        return states

    def _record_completed_day(self):
        if self.current_trading_day is None:
            return

        self.daily_history.append(
            {
                "date": self.current_trading_day,
                "equity_start": self.day_start_equity,
                "equity_end": self.account.equity,
                "realized_pnl": self.daily_closed_pnl,
                "realized_return_fraction": (
                    self.daily_closed_pnl / self.day_start_equity
                    if self.day_start_equity
                    else 0.0
                ),
                "entries_taken": self.daily_entries_taken,
                "closed_trades": self.daily_closed_trades,
                "threshold": self.current_threshold,
            }
        )

    def _open_r_multiple(self, trade, price):
        if not getattr(trade, "R", None):
            return 0.0
        if getattr(trade, "side", "long") == "short":
            return (float(trade.entry_price) - float(price)) / float(trade.R)
        return (float(price) - float(trade.entry_price)) / float(trade.R)

    def _risk_fraction_for_score(self, score, risk_mult=1.0):
        base = self.min_risk_per_trade + (
            clamp(score) * (self.max_risk_per_trade - self.min_risk_per_trade)
        )
        return min(self.max_risk_per_trade, max(0.0, base * float(risk_mult or 1.0)))

    def _score_bucket_risk_multiplier(self, score_bucket):
        return float(
            self.score_bucket_risk_multipliers.get(
                str(score_bucket or "<0.6"),
                0.0,
            )
            or 0.0
        )

    @staticmethod
    def _safe_float(value, default=0.0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def _convexity_enabled_for_candidate(self, candidate):
        if not self.convexity_enabled:
            return False
        if candidate.get("strategy_type", "core") not in self.convexity_strategy_types:
            return False
        if float(candidate.get("score", 0.0) or 0.0) < self.convexity_min_score:
            return False
        execution_profile = dict(candidate.get("execution_profile") or {})
        if bool(execution_profile.get("disable_pyramiding", False)):
            return False
        return True

    def _convexity_trend_supports_hold(self, row, side):
        price = self._safe_float(row.get("close"), default=0.0)
        fast_ema = self._safe_float(row.get(self.fast_ema_column), default=price)
        slow_ema = self._safe_float(row.get(self.slow_ema_column), default=fast_ema)
        session_vwap = self._safe_float(row.get("session_vwap"), default=price)
        if str(side).lower() == "short":
            return price <= fast_ema <= slow_ema and price <= session_vwap
        return price >= fast_ema >= slow_ema and price >= session_vwap

    def _convexity_quality_ok(
        self,
        row,
        *,
        side,
        min_body_strength,
        min_close_position,
        min_expansion,
    ):
        body_strength = self._safe_float(row.get("body_strength"), default=0.0)
        close_position = self._safe_float(row.get("close_position"), default=0.5)
        expansion = self._safe_float(
            row.get("range_expansion_factor"),
            default=0.0,
        )
        vwap_distance = abs(
            self._safe_float(row.get("vwap_distance_ratio"), default=0.0)
        )
        if body_strength < min_body_strength:
            return False
        if expansion < min_expansion:
            return False
        if vwap_distance > self.convexity_max_abs_vwap_distance:
            return False
        if str(side).lower() == "short":
            if close_position > (1.0 - min_close_position):
                return False
        elif close_position < min_close_position:
            return False
        return self._convexity_trend_supports_hold(row, side)

    def _convexity_promote_quality_ok(self, trade, row):
        return self._convexity_quality_ok(
            row,
            side=getattr(trade, "side", "long"),
            min_body_strength=self.convexity_min_body_strength,
            min_close_position=self.convexity_min_close_position,
            min_expansion=self.convexity_min_expansion,
        )

    def _convexity_add_quality_ok(self, trade, row):
        return self._convexity_quality_ok(
            row,
            side=getattr(trade, "side", "long"),
            min_body_strength=self.convexity_add_min_body_strength,
            min_close_position=self.convexity_add_min_close_position,
            min_expansion=self.convexity_add_min_expansion,
        )

    def _convexity_stop_for_add(self, trade, entry_price):
        stop_price = float(getattr(trade, "active_stop", trade.stop))
        if not self.convexity_use_active_stop_for_adds:
            return float(trade.stop)

        structural_distance = abs(float(entry_price) - float(trade.stop))
        minimum_distance = max(
            self.position_sizer._minimum_stop_distance(float(entry_price)),
            structural_distance * self.convexity_add_min_stop_distance_r_multiple,
        )
        if str(getattr(trade, "side", "long")).lower() == "short":
            minimum_stop = float(entry_price) + minimum_distance
            return max(stop_price, minimum_stop)
        maximum_stop = float(entry_price) - minimum_distance
        return min(stop_price, maximum_stop)

    def _convexity_target_risk_amount(self, trade, target_multiple):
        base_amount = self._safe_float(getattr(trade, "convexity_base_risk_amount", None))
        if base_amount <= 0.0:
            base_amount = self._safe_float(getattr(trade, "initial_risk_amount", None))
        return max(0.0, base_amount * float(target_multiple or 0.0))

    def _convexity_current_risk_amount(self, trade, stop_price):
        if self.convexity_use_active_stop_for_adds and stop_price == getattr(trade, "active_stop", None):
            return float(trade.total_risk_to_active_stop())
        return float(trade.total_risk_to_stop_price(stop_price, floor_zero=True))

    def _convexity_add_size(self, trade, entry_price, stop_price, target_multiple):
        target_risk_amount = self._convexity_target_risk_amount(trade, target_multiple)
        current_risk_amount = self._convexity_current_risk_amount(trade, stop_price)
        remaining_risk_amount = target_risk_amount - current_risk_amount
        if remaining_risk_amount <= 0.0:
            return 0.0

        risk_per_unit = abs(float(entry_price) - float(stop_price))
        minimum_stop_distance = self.position_sizer._minimum_stop_distance(float(entry_price))
        if risk_per_unit < minimum_stop_distance:
            return 0.0

        return remaining_risk_amount / risk_per_unit

    def _maybe_apply_convexity(self, trade, row, *, open_r_multiple):
        if not getattr(trade, "convexity_enabled", False):
            return False
        if len(getattr(trade, "entries", []) or []) >= self.convexity_max_layers:
            return False
        if int(getattr(trade, "bars_held", 0) or 0) <= int(getattr(trade, "convexity_last_add_bar", 0) or 0):
            return False
        if (
            int(getattr(trade, "bars_held", 0) or 0)
            - int(getattr(trade, "convexity_last_add_bar", 0) or 0)
        ) < self.convexity_min_bars_between_adds:
            return False

        stage = int(getattr(trade, "convexity_stage", 0) or 0)
        if stage <= 0:
            if open_r_multiple < self.convexity_promote_trigger_r:
                return False
            if not self._convexity_promote_quality_ok(trade, row):
                return False
            target_multiple = min(
                self.convexity_promote_target_multiple,
                self.convexity_max_target_multiple,
            )
            next_stage = 1
            next_state = "promoted"
        elif stage == 1:
            if open_r_multiple < self.convexity_add_trigger_r:
                return False
            if not self._convexity_add_quality_ok(trade, row):
                return False
            target_multiple = min(
                self.convexity_add_target_multiple,
                self.convexity_max_target_multiple,
            )
            next_stage = 2
            next_state = "expanded"
        else:
            return False

        entry_price = float(row["close"])
        stop_price = self._convexity_stop_for_add(trade, entry_price)
        add_size = self._convexity_add_size(
            trade,
            entry_price,
            stop_price,
            target_multiple,
        )
        if add_size <= 0.0:
            return False

        added_structural_risk = abs(float(entry_price) - float(trade.stop)) * float(add_size)
        added_risk_fraction = added_structural_risk / float(self.account.equity or 1.0)
        projected_total_risk = self._active_risk_fraction() + added_risk_fraction
        if projected_total_risk > self.max_total_risk_fraction:
            return False
        strategy_sleeve_cap = self._strategy_reserved_risk_fraction(
            getattr(trade, "strategy_type", "core")
        )
        if (
            strategy_sleeve_cap > 0.0
            and (
                self._active_strategy_risk_fraction(getattr(trade, "strategy_type", "core"))
                + added_risk_fraction
            ) > strategy_sleeve_cap
        ):
            return False

        risk_group = getattr(trade, "risk_group", None)
        group_cap = (
            getattr(trade, "conditions", {}).get("group_risk_cap")
            if isinstance(getattr(trade, "conditions", {}), dict)
            else None
        )
        if (
            risk_group
            and group_cap not in (None, "")
            and (
                self._active_risk_fraction(risk_group=risk_group)
                + added_risk_fraction
            ) > float(group_cap)
        ):
            return False

        trade.add_entry(entry_price, add_size)
        trade.pyramid_level = int(getattr(trade, "pyramid_level", 0) or 0) + 1
        trade.convexity_stage = next_stage
        trade.convexity_state = next_state
        trade.convexity_add_count = int(getattr(trade, "convexity_add_count", 0) or 0) + 1
        trade.convexity_last_add_bar = int(getattr(trade, "bars_held", 0) or 0)
        if trade.equity_at_entry:
            trade.effective_risk_fraction = (
                trade.total_risk_to_stop() / float(trade.equity_at_entry)
            )
            trade.conditions["effective_risk_fraction"] = trade.effective_risk_fraction
        trade.annotate_convexity_profile(
            enabled=True,
            state=trade.convexity_state,
            stage=trade.convexity_stage,
            base_risk_fraction=getattr(trade, "convexity_base_risk_fraction", None),
            probe_fraction=getattr(trade, "convexity_probe_fraction", None),
            target_risk_fraction=getattr(trade, "convexity_target_risk_fraction", None),
            base_risk_amount=getattr(trade, "convexity_base_risk_amount", None),
            promote_target_multiple=getattr(trade, "convexity_promote_target_multiple", None),
            add_target_multiple=getattr(trade, "convexity_add_target_multiple", None),
            max_target_multiple=getattr(trade, "convexity_max_target_multiple", None),
            add_count=trade.convexity_add_count,
            last_add_bar=trade.convexity_last_add_bar,
        )
        return True

    def _active_risk_fraction(self, risk_group=None):
        equity = float(self.account.equity or 0.0)
        if equity <= 0:
            return 0.0
        total = 0.0
        for trade in self.open_positions:
            if risk_group and getattr(trade, "risk_group", None) != risk_group:
                continue
            total += float(trade.total_risk_to_stop())
        return total / equity

    def _active_strategy_risk_fraction(self, strategy_type):
        equity = float(self.account.equity or 0.0)
        if equity <= 0:
            return 0.0
        normalized = str(strategy_type or "core")
        total = 0.0
        for trade in self.open_positions:
            if str(getattr(trade, "strategy_type", "core") or "core") != normalized:
                continue
            total += float(trade.total_risk_to_stop())
        return total / equity

    def _active_shared_risk_fraction(self):
        equity = float(self.account.equity or 0.0)
        if equity <= 0:
            return 0.0
        total = 0.0
        for trade in self.open_positions:
            strategy_type = str(getattr(trade, "strategy_type", "core") or "core")
            if self._strategy_reserved_risk_fraction(strategy_type) > 0.0:
                continue
            total += float(trade.total_risk_to_stop())
        return total / equity

    def _asset_open_count(self, symbol):
        return sum(1 for trade in self.open_positions if getattr(trade, "symbol", None) == symbol)

    def _direction_open_count(self, side):
        return sum(1 for trade in self.open_positions if getattr(trade, "side", None) == side)

    def _strategy_open_count(self, strategy_type):
        return sum(
            1
            for trade in self.open_positions
            if str(getattr(trade, "strategy_type", "core") or "core")
            == str(strategy_type or "core")
        )

    def _same_symbol_same_side_open(self, symbol, side):
        normalized_side = str(side or "long").lower()
        return any(
            getattr(trade, "symbol", None) == symbol
            and str(getattr(trade, "side", "long")).lower() == normalized_side
            for trade in self.open_positions
        )

    def _allowed_sides_for_strategy(self, strategy_type):
        strategy_type = str(strategy_type or "core")
        allowed = self.strategy_allowed_sides.get(strategy_type)
        if allowed:
            return allowed
        return self.allowed_sides

    def _strategy_sleeve_config(self, strategy_type):
        return self.strategy_sleeves.get(str(strategy_type or "core"), {})

    def _strategy_reserved_risk_fraction(self, strategy_type):
        sleeve = self._strategy_sleeve_config(strategy_type)
        return float(sleeve.get("reserved_risk_fraction", 0.0) or 0.0)

    def _allocator_v2_sleeve_config(self, strategy_type):
        return self.allocator_v2_sleeves.get(
            str(strategy_type or "core"),
            {
                "priority_multiplier": 1.0,
                "rank_weights": [1.0],
                "max_candidates": 1,
                "max_risk_fraction_multiplier": 1.0,
                "absolute_max_risk_fraction": None,
            },
        )

    def _symbol_has_other_strategy_open(self, symbol, strategy_type):
        normalized = str(strategy_type or "core")
        return any(
            getattr(trade, "symbol", None) == symbol
            and str(getattr(trade, "strategy_type", "core") or "core") != normalized
            for trade in self.open_positions
        )

    @staticmethod
    def _is_htf_strategy_type(strategy_type):
        normalized = str(strategy_type or "")
        return normalized.startswith("htf_12h_") or normalized.startswith("h6_")

    def _manage_htf_trade(self, trade, row, htf_context):
        active_stop = float(getattr(trade, "active_stop", trade.stop))
        if self.exit_engine.should_exit(row, active_stop, side=trade.side):
            exit_reason = "htf trailing stop" if active_stop != trade.stop else "htf hard exit"
            self.close_trade(trade, row, reason=exit_reason, exit_price=active_stop)
            return True

        max_hold_candles = getattr(trade, "max_hold_candles", None)
        if max_hold_candles is not None and int(getattr(trade, "bars_held", 0) or 0) >= int(max_hold_candles):
            self.close_trade(trade, row, reason="htf time exit")
            return True

        if not htf_context:
            return False

        side = str(getattr(trade, "side", "long")).lower()
        state_key = f"htf_trailing_state_{side}"
        stop_key = f"htf_trailing_{side}"
        decay_key = f"htf_decay_active_{side}"
        context_1d = str(htf_context.get("htf_context_1d", "neutral") or "neutral")
        context_1w = str(htf_context.get("htf_context_1w", "neutral") or "neutral")
        trailing_state = str(htf_context.get(state_key, "init") or "init")
        decay_active = bool(htf_context.get(decay_key, False))
        trailing_stop = self._safe_float(
            htf_context.get(stop_key, getattr(trade, "active_stop", trade.stop)),
            default=float(getattr(trade, "active_stop", trade.stop)),
        )

        trade.annotate_htf_context(
            signal_family=getattr(trade, "htf_signal_family", None),
            htf_score=getattr(trade, "htf_score", None),
            context_1d=context_1d,
            context_1w=context_1w,
            entry_reason=getattr(trade, "htf_entry_reason", None),
            stop_reason=getattr(trade, "htf_stop_reason", None),
            trailing_state=trailing_state,
            decay_reason=("macro_decay" if decay_active else None),
            candidate_rank=getattr(trade, "htf_candidate_rank", None),
        )

        if side == "short":
            trade.active_stop = min(float(trade.active_stop), trailing_stop)
        else:
            trade.active_stop = max(float(trade.active_stop), trailing_stop)

        if decay_active:
            decay_count = int(getattr(trade, "conditions", {}).get("htf_decay_count", 0) or 0) + 1
            trade.conditions["htf_decay_count"] = decay_count
            if decay_count >= int(htf_context.get("htf_decay_12h_candles", 3) or 3):
                trade.annotate_htf_context(
                    signal_family=getattr(trade, "htf_signal_family", None),
                    htf_score=getattr(trade, "htf_score", None),
                    context_1d=context_1d,
                    context_1w=context_1w,
                    entry_reason=getattr(trade, "htf_entry_reason", None),
                    stop_reason=getattr(trade, "htf_stop_reason", None),
                    trailing_state=trailing_state,
                    decay_reason="persistent_htf_decay",
                    candidate_rank=getattr(trade, "htf_candidate_rank", None),
                )
                self.close_trade(trade, row, reason="htf decay exit")
                return True
        else:
            trade.conditions["htf_decay_count"] = 0

        return False

    def _elapsed_day_fraction(self, timestamp):
        seconds = (
            timestamp.hour * 3600
            + timestamp.minute * 60
            + timestamp.second
        )
        return clamp(seconds / float(24 * 3600))

    def _normalize_time_value(self, value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        converter = getattr(value, "to_pydatetime", None)
        if callable(converter):
            return converter()
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _stats_from_records(self, records):
        count = len(records)
        wins = sum(1 for record in records if float(record.get("pnl", 0.0) or 0.0) > 0.0)
        total_r = sum(float(record.get("pnl_R_initial", 0.0) or 0.0) for record in records)
        total_pnl = sum(float(record.get("pnl", 0.0) or 0.0) for record in records)
        gross_profit = sum(
            float(record.get("pnl", 0.0) or 0.0)
            for record in records
            if float(record.get("pnl", 0.0) or 0.0) > 0.0
        )
        gross_loss = -sum(
            float(record.get("pnl", 0.0) or 0.0)
            for record in records
            if float(record.get("pnl", 0.0) or 0.0) < 0.0
        )
        return {
            "count": count,
            "wins": wins,
            "total_R": total_r,
            "total_pnl": total_pnl,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "profit_factor": (gross_profit / gross_loss) if gross_loss > 0.0 else (float("inf") if gross_profit > 0.0 else 0.0),
            "avg_R": (total_r / count) if count else 0.0,
            "win_rate": (wins / count) if count else 0.0,
        }

    def _trim_performance_history(self):
        if self.performance_history_limit <= 0:
            return
        if len(self.performance_history) <= self.performance_history_limit:
            return
        self.performance_history = self.performance_history[-self.performance_history_limit :]

    def _refresh_recent_performance(self):
        all_records = [
            record
            for record in self.performance_history
            if record.get("exit_time") is not None
        ]
        if not all_records:
            self.recent_score_stats = {}
            self.recent_score_trade_stats = {}
            self.recent_strategy_stats = {}
            self.recent_strategy_trade_stats = {}
            return

        latest_time = max(record["exit_time"] for record in all_records)
        cutoff = None
        if self.recency_lookback_days > 0:
            cutoff = latest_time - timedelta(days=self.recency_lookback_days)

        bucket_records = defaultdict(list)
        strategy_records = defaultdict(list)
        strategy_bucket_records = defaultdict(list)
        for record in all_records:
            bucket = str(record.get("score_bucket") or "<0.6")
            strategy_type = str(record.get("strategy_type") or "core")
            bucket_records[bucket].append(record)
            strategy_records[strategy_type].append(record)
            strategy_bucket_records[(strategy_type, bucket)].append(record)

        self.recent_score_stats = {
            bucket: self._stats_from_records(
                [
                    record
                    for record in group
                    if cutoff is None or record["exit_time"] >= cutoff
                ]
            )
            for bucket, group in bucket_records.items()
        }
        self.recent_score_trade_stats = {
            bucket: self._stats_from_records(
                group[-self.recency_max_trades :]
                if self.recency_max_trades > 0 and len(group) > self.recency_max_trades
                else group
            )
            for bucket, group in bucket_records.items()
        }
        self.recent_strategy_stats = {
            strategy_type: self._stats_from_records(
                [
                    record
                    for record in group
                    if cutoff is None or record["exit_time"] >= cutoff
                ]
            )
            for strategy_type, group in strategy_records.items()
        }
        self.recent_strategy_trade_stats = {
            strategy_type: self._stats_from_records(
                group[-self.recency_max_trades :]
                if self.recency_max_trades > 0 and len(group) > self.recency_max_trades
                else group
            )
            for strategy_type, group in strategy_records.items()
        }
        self.recent_strategy_bucket_stats = {
            f"{strategy_type}|{bucket}": self._stats_from_records(
                [
                    record
                    for record in group
                    if cutoff is None or record["exit_time"] >= cutoff
                ]
            )
            for (strategy_type, bucket), group in strategy_bucket_records.items()
        }
        self.recent_strategy_bucket_trade_stats = {
            f"{strategy_type}|{bucket}": self._stats_from_records(
                group[-self.recency_max_trades :]
                if self.recency_max_trades > 0 and len(group) > self.recency_max_trades
                else group
            )
            for (strategy_type, bucket), group in strategy_bucket_records.items()
        }

    def _record_trade_performance(self, trade):
        self.performance_history.append(
            {
                "exit_time": self._normalize_time_value(getattr(trade, "exit_time", None)),
                "strategy_type": str(getattr(trade, "strategy_type", "core") or "core"),
                "score_bucket": str(
                    getattr(trade, "score_bucket", None)
                    or score_bucket_label(getattr(trade, "opportunity_score", 0.0) or 0.0)
                ),
                "pnl_R_initial": float(getattr(trade, "pnl_R_initial", 0.0) or 0.0),
                "pnl": float(getattr(trade, "pnl", 0.0) or 0.0),
            }
        )
        self._trim_performance_history()
        self._refresh_recent_performance()

    def _expanded_cumulative_stats(self, values):
        if not values:
            return None
        count = int(values.get("count", 0) or 0)
        wins = int(values.get("wins", 0) or 0)
        total_r = float(values.get("total_R", 0.0) or 0.0)
        total_pnl = float(values.get("total_pnl", 0.0) or 0.0)
        return {
            "count": count,
            "wins": wins,
            "total_R": total_r,
            "total_pnl": total_pnl,
            "avg_R": (total_r / count) if count else 0.0,
            "win_rate": (wins / count) if count else 0.0,
        }

    def _effective_bucket_stats(self, bucket):
        bucket = str(bucket or "<0.6")
        recent = self.recent_score_stats.get(bucket)
        if recent and int(recent.get("count", 0) or 0) >= self.recency_min_bucket_trades:
            return recent, "recent_window"
        recent_trade = self.recent_score_trade_stats.get(bucket)
        if recent_trade and int(recent_trade.get("count", 0) or 0) >= self.recency_min_bucket_trades:
            return recent_trade, "recent_trades"
        cumulative = self._expanded_cumulative_stats(self.score_stats.get(bucket))
        if cumulative and int(cumulative.get("count", 0) or 0) >= self.min_profitable_bucket_count:
            return cumulative, "cumulative"
        return None, "none"

    def _effective_strategy_stats(self, strategy_type):
        strategy_type = str(strategy_type or "core")
        profile = self._strategy_health_profile(strategy_type)
        min_trades = int(profile["recency_min_trades"])
        recent = self._strategy_stats_for_window(
            strategy_type,
            lookback_days=profile["recency_lookback_days"],
            max_trades=0,
        )
        if recent and int(recent.get("count", 0) or 0) >= min_trades:
            return recent, "recent_window"
        recent_trade = self._strategy_stats_for_window(
            strategy_type,
            lookback_days=0,
            max_trades=profile["recency_max_trades"],
        )
        if recent_trade and int(recent_trade.get("count", 0) or 0) >= min_trades:
            return recent_trade, "recent_trades"
        cumulative = self._expanded_cumulative_stats(self.strategy_stats.get(strategy_type))
        if cumulative and int(cumulative.get("count", 0) or 0) >= min_trades:
            return cumulative, "cumulative"
        return None, "none"

    def _strategy_health_profile(self, strategy_type):
        strategy_type = str(strategy_type or "core")
        raw = dict(self.strategy_health_profiles.get(strategy_type, {}) or {})
        return {
            "recency_lookback_days": int(
                raw.get("recency_lookback_days", self.recency_lookback_days)
            ),
            "recency_max_trades": int(
                raw.get("recency_max_trades", self.recency_max_trades)
            ),
            "recency_min_trades": int(
                raw.get("recency_min_trades", self.recency_min_strategy_trades)
            ),
            "neutral_below_min_trades": bool(raw.get("neutral_below_min_trades", False)),
            "disable_when_negative": bool(
                raw.get("disable_when_negative", self.disable_non_core_negative_strategies)
            ),
            "negative_risk_multiplier": float(
                raw.get("negative_risk_multiplier", self.strategy_negative_risk_multiplier)
            ),
            "positive_floor_multiplier": float(
                raw.get("positive_floor_multiplier", self.strategy_positive_floor_multiplier)
            ),
            "positive_cap": float(
                raw.get("positive_cap", self.strategy_positive_cap)
            ),
            "emergency_disable_min_trades": int(
                raw.get("emergency_disable_min_trades", self.strategy_emergency_disable_min_trades)
            ),
            "emergency_disable_avg_r": float(
                raw.get("emergency_disable_avg_r", self.strategy_emergency_disable_avg_r)
            ),
        }

    @staticmethod
    def _strategy_bucket_key(strategy_type, bucket):
        return f"{str(strategy_type or 'core')}|{str(bucket or '<0.6')}"

    def _strategy_bucket_health_profile(self, strategy_type):
        strategy_type = str(strategy_type or "core")
        raw = dict(self.strategy_bucket_health_profiles.get(strategy_type, {}) or {})
        return {
            "enabled": bool(raw.get("enabled", bool(raw))),
            "recency_lookback_days": int(
                raw.get("recency_lookback_days", self.recency_lookback_days)
            ),
            "recency_max_trades": int(
                raw.get("recency_max_trades", self.recency_max_trades)
            ),
            "recency_min_trades": int(
                raw.get("recency_min_trades", self.recency_min_bucket_trades)
            ),
            "neutral_below_min_trades": bool(raw.get("neutral_below_min_trades", True)),
            "disable_when_negative": bool(raw.get("disable_when_negative", False)),
            "negative_risk_multiplier": float(
                raw.get("negative_risk_multiplier", self.bucket_negative_risk_multiplier)
            ),
            "positive_floor_multiplier": float(
                raw.get(
                    "positive_floor_multiplier",
                    self.bucket_positive_floor_multiplier,
                )
            ),
            "positive_cap": float(
                raw.get("positive_cap", self.bucket_positive_cap)
            ),
            "apply_to_threshold_derivation": bool(
                raw.get("apply_to_threshold_derivation", strategy_type == "core")
            ),
        }

    def _strategy_stats_for_window(self, strategy_type, *, lookback_days, max_trades):
        strategy_type = str(strategy_type or "core")
        records = [
            record
            for record in self.performance_history
            if record.get("exit_time") is not None
            and str(record.get("strategy_type") or "core") == strategy_type
        ]
        if not records:
            return None
        if lookback_days > 0:
            latest_time = max(record["exit_time"] for record in records)
            cutoff = latest_time - timedelta(days=int(lookback_days))
            records = [record for record in records if record["exit_time"] >= cutoff]
        if max_trades > 0 and len(records) > int(max_trades):
            records = records[-int(max_trades):]
        return self._stats_from_records(records)

    def strategy_runtime_policy_state(self, strategy_type, guard_config=None):
        strategy_type = str(strategy_type or "core")
        guard = dict(guard_config or {})
        if not bool(guard.get("enabled", False)):
            return {
                "enabled": False,
                "label": "guard_disabled",
                "fallback_to_short_only": False,
                "count": 0,
                "avg_R": 0.0,
                "profit_factor": 0.0,
            }
        stats = self._strategy_stats_for_window(
            strategy_type,
            lookback_days=int(guard.get("lookback_days", 0) or 0),
            max_trades=int(guard.get("max_trades", 0) or 0),
        ) or {}
        count = int(stats.get("count", 0) or 0)
        min_trades = int(guard.get("min_trades", 0) or 0)
        avg_r = float(stats.get("avg_R", 0.0) or 0.0)
        profit_factor = float(stats.get("profit_factor", 0.0) or 0.0)
        min_avg_r = float(guard.get("min_avg_R", 0.0) or 0.0)
        min_profit_factor = float(guard.get("min_profit_factor", 0.0) or 0.0)
        has_sufficient_history = count >= min_trades
        fallback_to_short_only = bool(
            has_sufficient_history
            and (
                avg_r < min_avg_r
                or profit_factor < min_profit_factor
            )
        )
        if not has_sufficient_history:
            label = "insufficient_history"
        elif fallback_to_short_only:
            label = "fallback_short_only"
        else:
            label = "boost_active"
        return {
            "enabled": True,
            "label": label,
            "fallback_to_short_only": fallback_to_short_only,
            "count": count,
            "avg_R": avg_r,
            "profit_factor": profit_factor,
            "min_trades": min_trades,
            "min_avg_R": min_avg_r,
            "min_profit_factor": min_profit_factor,
        }

    def _strategy_bucket_stats_for_window(self, strategy_type, score_bucket, *, lookback_days, max_trades):
        strategy_type = str(strategy_type or "core")
        score_bucket = str(score_bucket or "<0.6")
        records = [
            record
            for record in self.performance_history
            if record.get("exit_time") is not None
            and str(record.get("strategy_type") or "core") == strategy_type
            and str(record.get("score_bucket") or "<0.6") == score_bucket
        ]
        if not records:
            return None
        if lookback_days > 0:
            latest_time = max(record["exit_time"] for record in records)
            cutoff = latest_time - timedelta(days=int(lookback_days))
            records = [record for record in records if record["exit_time"] >= cutoff]
        if max_trades > 0 and len(records) > int(max_trades):
            records = records[-int(max_trades):]
        return self._stats_from_records(records)

    def _health_multiplier_from_avg_r(
        self,
        avg_r,
        *,
        negative_multiplier,
        positive_floor_multiplier,
        positive_cap,
    ):
        avg_r = float(avg_r or 0.0)
        if avg_r <= 0.0:
            return float(negative_multiplier)
        if self.health_reference_avg_r <= 0.0:
            return 1.0
        scaled = avg_r / self.health_reference_avg_r
        return clamp(
            scaled,
            minimum=positive_floor_multiplier,
            maximum=positive_cap,
        )

    def _bucket_health_multiplier(self, score_bucket):
        stats, source = self._effective_bucket_stats(score_bucket)
        if not stats:
            return 1.0, source
        return (
            self._health_multiplier_from_avg_r(
                stats.get("avg_R", 0.0),
                negative_multiplier=self.bucket_negative_risk_multiplier,
                positive_floor_multiplier=self.bucket_positive_floor_multiplier,
                positive_cap=self.bucket_positive_cap,
            ),
            source,
        )

    def _effective_strategy_bucket_stats(self, strategy_type, score_bucket):
        profile = self._strategy_bucket_health_profile(strategy_type)
        if not profile["enabled"]:
            return None, "disabled"
        recent = self._strategy_bucket_stats_for_window(
            strategy_type,
            score_bucket,
            lookback_days=profile["recency_lookback_days"],
            max_trades=0,
        )
        if recent and int(recent.get("count", 0) or 0) >= int(profile["recency_min_trades"]):
            return recent, "recent_window"
        recent_trade = self._strategy_bucket_stats_for_window(
            strategy_type,
            score_bucket,
            lookback_days=0,
            max_trades=profile["recency_max_trades"],
        )
        if recent_trade and int(recent_trade.get("count", 0) or 0) >= int(profile["recency_min_trades"]):
            return recent_trade, "recent_trades"
        return None, "none"

    def _strategy_bucket_health_multiplier(self, strategy_type, score_bucket):
        profile = self._strategy_bucket_health_profile(strategy_type)
        if not profile["enabled"]:
            return 1.0, "disabled"
        stats, source = self._effective_strategy_bucket_stats(strategy_type, score_bucket)
        if not stats:
            return 1.0, source
        count = int(stats.get("count", 0) or 0)
        if profile["neutral_below_min_trades"] and count < int(profile["recency_min_trades"]):
            return 1.0, f"{source}_neutral_sparse"
        avg_r = float(stats.get("avg_R", 0.0) or 0.0)
        if profile["disable_when_negative"] and avg_r < 0.0 and count >= int(profile["recency_min_trades"]):
            return 0.0, source
        return (
            self._health_multiplier_from_avg_r(
                avg_r,
                negative_multiplier=profile["negative_risk_multiplier"],
                positive_floor_multiplier=profile["positive_floor_multiplier"],
                positive_cap=profile["positive_cap"],
            ),
            source,
        )

    def _strategy_health_multiplier(self, strategy_type):
        strategy_type = str(strategy_type or "core")
        profile = self._strategy_health_profile(strategy_type)
        recent_window = self._strategy_stats_for_window(
            strategy_type,
            lookback_days=profile["recency_lookback_days"],
            max_trades=0,
        ) or {}
        recent_window_count = int(recent_window.get("count", 0) or 0)
        recent_window_avg_r = float(recent_window.get("avg_R", 0.0) or 0.0)
        if (
            strategy_type != "core"
            and profile["disable_when_negative"]
            and recent_window_count >= int(profile["emergency_disable_min_trades"])
            and recent_window_avg_r <= float(profile["emergency_disable_avg_r"])
        ):
            return 0.0, "recent_emergency"

        stats, source = self._effective_strategy_stats(strategy_type)
        if not stats:
            return 1.0, source
        if (
            profile["neutral_below_min_trades"]
            and int(stats.get("count", 0) or 0) < int(profile["recency_min_trades"])
        ):
            return 1.0, f"{source}_neutral_sparse"
        avg_r = float(stats.get("avg_R", 0.0) or 0.0)
        if (
            strategy_type != "core"
            and profile["disable_when_negative"]
            and avg_r < 0.0
            and int(stats.get("count", 0) or 0) >= int(profile["recency_min_trades"])
        ):
            return 0.0, source
        return (
            self._health_multiplier_from_avg_r(
                avg_r,
                negative_multiplier=profile["negative_risk_multiplier"],
                positive_floor_multiplier=profile["positive_floor_multiplier"],
                positive_cap=profile["positive_cap"],
            ),
            source,
        )

    def _derive_threshold_from_history(self):
        profitable_floors = []
        threshold_source = "base"
        for bucket, static_multiplier in self.score_bucket_risk_multipliers.items():
            if float(static_multiplier or 0.0) <= 0.0:
                continue
            core_bucket_profile = self._strategy_bucket_health_profile("core")
            if core_bucket_profile["enabled"] and core_bucket_profile["apply_to_threshold_derivation"]:
                stats, source = self._effective_strategy_bucket_stats("core", bucket)
            else:
                stats, source = self._effective_bucket_stats(bucket)
            if not stats:
                continue
            count = int(stats["count"])
            if count < self.min_profitable_bucket_count:
                continue
            avg_r = float(stats.get("avg_R", 0.0) or 0.0)
            if avg_r > 0.0:
                profitable_floors.append(bucket_floor(bucket))
                if str(source).startswith("recent"):
                    threshold_source = "recent"

        if not profitable_floors:
            return self.base_threshold, "base"

        return min(profitable_floors), threshold_source

    def _update_threshold_for_new_day(self):
        derived, source = self._derive_threshold_from_history()
        if self.current_trading_day is not None:
            if self.daily_entries_taken < self.min_trades_per_day:
                derived -= self.pacing_relax_step
            elif self.daily_entries_taken > self.max_trades_per_day:
                derived += self.pacing_tighten_step
        derived = clamp(derived, self.min_threshold, self.max_threshold)
        self.current_threshold_floor = derived
        self.current_threshold_source = source
        self.current_threshold = (
            (1.0 - self.threshold_smoothing) * self.current_threshold
            + self.threshold_smoothing * derived
        )
        self.current_threshold = clamp(
            self.current_threshold,
            self.min_threshold,
            self.max_threshold,
        )

    def _maybe_update_score_weights(self):
        total_trades = sum(stats["count"] for stats in self.score_stats.values())
        if total_trades < self.weight_update_min_trades:
            return
        self.scorer.update_weights(self.feature_stats)

    def reset_daily_state_if_needed(self, timestamp):
        current_day = timestamp.date()
        if self.current_trading_day == current_day:
            return

        self._record_completed_day()
        self._update_threshold_for_new_day()
        self._maybe_update_score_weights()
        self.current_trading_day = current_day
        self.day_start_equity = self.account.equity
        self.daily_entries_taken = 0
        self.daily_closed_trades = 0
        self.daily_closed_pnl = 0.0
        self.daily_loss_streak = 0

    def adaptive_threshold(self, timestamp):
        threshold = float(self.current_threshold)
        elapsed_fraction = self._elapsed_day_fraction(timestamp)
        expected_trades = elapsed_fraction * float(self.target_trades_per_day)

        if self.daily_entries_taken < expected_trades:
            threshold -= self.pacing_relax_step
        elif self.daily_entries_taken > expected_trades + 1.0:
            threshold += self.pacing_tighten_step

        if self.daily_entries_taken >= self.max_trades_per_day:
            threshold = 1.01

        return clamp(threshold, self.min_threshold, 1.01)

    def _threshold_for_candidate(self, candidate, timestamp):
        threshold = float(self.adaptive_threshold(timestamp))
        strategy_type = str(candidate.get("strategy_type", "core") or "core")
        threshold += float(
            candidate.get(
                "selection_threshold_offset",
                self.strategy_threshold_offsets.get(strategy_type, 0.0),
            )
            or 0.0
        )
        min_threshold = float(
            candidate.get("selection_min_threshold", self.min_threshold) or self.min_threshold
        )
        max_threshold = float(
            candidate.get("selection_max_threshold", 1.01) or 1.01
        )
        return clamp(threshold, min_threshold, max_threshold)

    def build_signal_log_row(self, candidate, *, threshold, selected, selection_reason):
        return {
            "timestamp": candidate.get("timestamp"),
            "symbol": candidate.get("symbol"),
            "side": candidate.get("side"),
            "edge_type": candidate.get("edge_type"),
            "bias": candidate.get("bias"),
            "body_bucket": candidate.get("body_bucket"),
            "vwap_bucket": candidate.get("vwap_bucket"),
            "bucket_key": candidate.get("bucket_key_text"),
            "is_top_mover": candidate.get("is_top_mover"),
            "momentum_rank": candidate.get("momentum_rank"),
            "score": candidate.get("score"),
            "selection_score": candidate.get("selection_score"),
            "score_bucket": candidate.get("score_bucket"),
            "strategy_type": candidate.get("strategy_type"),
            "risk_group": candidate.get("risk_group"),
            "moonshot_score": candidate.get("moonshot_score"),
            "range_expansion_factor": candidate.get("range_expansion_factor"),
            "htf_signal_family": candidate.get("htf_signal_family"),
            "htf_score": candidate.get("htf_score"),
            "htf_context_1d": candidate.get("htf_context_1d"),
            "htf_context_1w": candidate.get("htf_context_1w"),
            "htf_entry_reason": candidate.get("htf_entry_reason"),
            "htf_stop_reason": candidate.get("htf_stop_reason"),
            "htf_trailing_state": candidate.get("htf_trailing_state"),
            "htf_decay_reason": candidate.get("htf_decay_reason"),
            "htf_candidate_rank": candidate.get("htf_candidate_rank"),
            "threshold": threshold,
            "selected": selected,
            "selection_reason": selection_reason,
            "strategy_sleeve_cap": candidate.get("strategy_sleeve_cap"),
            "shared_pool_cap": candidate.get("shared_pool_cap"),
            "bucket_valid": candidate.get("bucket_valid"),
            "bucket_expected_return": candidate.get("bucket_expected_return"),
            "bucket_risk_mult": candidate.get("bucket_risk_mult"),
            "bucket_health_mult": candidate.get("bucket_health_mult"),
            "bucket_health_source": candidate.get("bucket_health_source"),
            "strategy_health_mult": candidate.get("strategy_health_mult"),
            "strategy_health_source": candidate.get("strategy_health_source"),
            "allocation_sleeve": candidate.get("allocation_sleeve"),
            "allocation_priority": candidate.get("allocation_priority"),
            "allocation_rank": candidate.get("allocation_rank"),
            "allocated_risk_fraction": candidate.get("allocated_risk_fraction"),
            "agreement_bonus": candidate.get("agreement_bonus"),
            "leader_dominance_boost": candidate.get("leader_dominance_boost"),
            "allocation_brake_active": candidate.get("allocation_brake_active"),
            "allocation_brake_severity": candidate.get("allocation_brake_severity"),
            "coordination_active": candidate.get("coordination_active"),
            "coordination_rule": candidate.get("coordination_rule"),
            "coordination_context_1d": candidate.get("coordination_context_1d"),
            "coordination_priority_multiplier": candidate.get(
                "coordination_priority_multiplier"
            ),
            "coordination_base_risk_multiplier": candidate.get(
                "coordination_base_risk_multiplier"
            ),
            "coordination_sleeve_cap_multiplier": candidate.get(
                "coordination_sleeve_cap_multiplier"
            ),
        }

    def _allocator_cross_sleeve_adjustment(self, candidate, strategy_type):
        context_1d = str(candidate.get("htf_context_1d", "neutral") or "neutral").lower()
        side = str(candidate.get("side", "long") or "long").lower()
        identity = {
            "active": False,
            "rule": None,
            "context_1d": context_1d,
            "priority_multiplier": 1.0,
            "base_risk_multiplier": 1.0,
            "sleeve_cap_multiplier": 1.0,
        }
        if not self.allocator_v2_cross_sleeve_enabled:
            return identity

        rule_name = None
        if strategy_type == "h1_execution" and side == "short" and context_1d == "bearish":
            rule_name = "h1_bearish_short"
        elif strategy_type == "core" and side == "long" and context_1d == "bearish":
            rule_name = "core_bearish_countertrend_long"
        if not rule_name:
            return identity

        rule = dict(self.allocator_v2_cross_sleeve_rules.get(rule_name, {}) or {})
        if not rule:
            return identity
        return {
            "active": True,
            "rule": rule_name,
            "context_1d": context_1d,
            "priority_multiplier": float(rule.get("priority_multiplier", 1.0) or 1.0),
            "base_risk_multiplier": float(rule.get("base_risk_multiplier", 1.0) or 1.0),
            "sleeve_cap_multiplier": float(
                rule.get("sleeve_cap_multiplier", 1.0) or 1.0
            ),
        }

    def _build_candidate_selection_state(self, candidate, timestamp, candidate_id):
        threshold = float(self._threshold_for_candidate(candidate, timestamp))
        score = float(candidate.get("score", 0.0) or 0.0)
        selection_score = float(
            candidate.get("selection_score", candidate.get("score", 0.0)) or 0.0
        )
        score_bucket = candidate.get("score_bucket")
        strategy_type = str(candidate.get("strategy_type", "core") or "core")
        apply_score_bucket_filters = bool(
            candidate.get("apply_score_bucket_filters", True)
        )
        if apply_score_bucket_filters:
            base_bucket_risk_mult = self._score_bucket_risk_multiplier(score_bucket)
            bucket_health_mult, bucket_health_source = self._bucket_health_multiplier(
                score_bucket
            )
            strategy_bucket_health_mult, strategy_bucket_health_source = (
                self._strategy_bucket_health_multiplier(strategy_type, score_bucket)
            )
        else:
            base_bucket_risk_mult = 1.0
            bucket_health_mult, bucket_health_source = 1.0, "bypass"
            strategy_bucket_health_mult, strategy_bucket_health_source = 1.0, "bypass"

        strategy_health_mult, strategy_health_source = self._strategy_health_multiplier(
            strategy_type
        )
        effective_bucket_risk_mult = (
            base_bucket_risk_mult
            * bucket_health_mult
            * strategy_bucket_health_mult
        )
        risk_group = candidate.get("risk_group")
        group_risk_cap = candidate.get("group_risk_cap")
        max_strategy_positions = candidate.get("max_open_positions_for_strategy")
        block_same_symbol_same_side = bool(
            candidate.get("block_same_symbol_same_side", False)
        )
        sleeve_config = self._strategy_sleeve_config(strategy_type)
        strategy_sleeve_cap = float(
            candidate.get(
                "strategy_sleeve_cap",
                sleeve_config.get("reserved_risk_fraction", 0.0),
            )
            or 0.0
        )
        strategy_step_cap = candidate.get(
            "max_new_positions_per_step_for_strategy",
            sleeve_config.get("max_new_positions_per_step"),
        )
        block_if_symbol_has_other_strategy = bool(
            candidate.get(
                "block_if_symbol_has_other_strategy_position",
                sleeve_config.get("block_if_symbol_has_other_strategy_position", False),
            )
        )
        ignore_global_step_cap = bool(
            candidate.get(
                "ignore_global_step_cap",
                sleeve_config.get("ignore_global_step_cap", False),
            )
        )

        candidate["bucket_health_mult"] = bucket_health_mult
        candidate["bucket_health_source"] = bucket_health_source
        candidate["strategy_health_mult"] = strategy_health_mult
        candidate["strategy_health_source"] = strategy_health_source
        candidate["strategy_bucket_health_mult"] = strategy_bucket_health_mult
        candidate["strategy_bucket_health_source"] = strategy_bucket_health_source
        candidate["strategy_sleeve_cap"] = strategy_sleeve_cap
        candidate["shared_pool_cap"] = self.shared_pool_risk_fraction_cap
        candidate["allocation_sleeve"] = strategy_type

        allowed_sides = self._allowed_sides_for_strategy(strategy_type)
        reason = None
        if str(candidate.get("side") or "long").lower() not in allowed_sides:
            reason = "side_disabled"
        elif apply_score_bucket_filters and effective_bucket_risk_mult <= 0.0:
            reason = "score_bucket_filtered"
        elif apply_score_bucket_filters and strategy_bucket_health_mult <= 0.0:
            reason = "strategy_bucket_filtered"
        elif strategy_health_mult <= 0.0:
            reason = "strategy_health_filtered"
        elif (
            apply_score_bucket_filters
            and strategy_type == "core"
            and bucket_health_mult <= 0.0
        ):
            reason = "score_bucket_filtered"
        elif selection_score < threshold:
            reason = "score_below_threshold"
        elif (
            block_if_symbol_has_other_strategy
            and self._symbol_has_other_strategy_open(candidate["symbol"], strategy_type)
        ):
            reason = "symbol_strategy_conflict"
        elif self._asset_open_count(candidate["symbol"]) >= self.max_trades_per_asset:
            reason = "asset_cap"
        elif (
            max_strategy_positions not in (None, "")
            and self._strategy_open_count(strategy_type) >= int(max_strategy_positions)
        ):
            reason = "strategy_position_cap"
        elif (
            block_same_symbol_same_side
            and self._same_symbol_same_side_open(
                candidate["symbol"], candidate.get("side")
            )
        ):
            reason = "same_symbol_same_side_cap"
        elif self._direction_open_count(candidate["side"]) >= self.max_same_direction_positions:
            reason = "direction_cap"

        if candidate.get("risk_fraction_override") not in (None, ""):
            base_risk_fraction = float(candidate.get("risk_fraction_override")) * float(
                strategy_health_mult
            )
        else:
            base_risk_fraction = self._risk_fraction_for_score(
                score,
                risk_mult=(
                    float(candidate.get("risk_mult", 1.0) or 1.0)
                    * effective_bucket_risk_mult
                    * float(strategy_health_mult)
                ),
            )
        coordination = self._allocator_cross_sleeve_adjustment(candidate, strategy_type)
        base_risk_fraction *= float(coordination["base_risk_multiplier"])
        if strategy_sleeve_cap > 0.0:
            strategy_sleeve_cap *= float(coordination["sleeve_cap_multiplier"])
        convexity_enabled = self._convexity_enabled_for_candidate(candidate)
        candidate["strategy_sleeve_cap"] = strategy_sleeve_cap
        candidate["coordination_active"] = bool(coordination["active"])
        candidate["coordination_rule"] = coordination["rule"]
        candidate["coordination_context_1d"] = coordination["context_1d"]
        candidate["coordination_priority_multiplier"] = float(
            coordination["priority_multiplier"]
        )
        candidate["coordination_base_risk_multiplier"] = float(
            coordination["base_risk_multiplier"]
        )
        candidate["coordination_sleeve_cap_multiplier"] = float(
            coordination["sleeve_cap_multiplier"]
        )

        return {
            "id": candidate_id,
            "candidate": candidate,
            "threshold": threshold,
            "score": score,
            "selection_score": selection_score,
            "score_bucket": score_bucket,
            "strategy_type": strategy_type,
            "risk_group": risk_group,
            "group_risk_cap": group_risk_cap,
            "strategy_sleeve_cap": strategy_sleeve_cap,
            "strategy_step_cap": strategy_step_cap,
            "ignore_global_step_cap": ignore_global_step_cap,
            "base_risk_fraction": float(base_risk_fraction or 0.0),
            "coordination_priority_multiplier": float(
                coordination["priority_multiplier"]
            ),
            "convexity_enabled": convexity_enabled,
            "probe_risk_fraction": (
                float(base_risk_fraction or 0.0) * self.convexity_probe_fraction
                if convexity_enabled
                else float(base_risk_fraction or 0.0)
            ),
            "reason": reason,
        }

    def _build_allocator_agreement_bonus_map(self, states):
        bonuses = defaultdict(float)
        if not self.allocator_v2_enabled or not self.allocator_v2_agreement_enabled:
            return bonuses

        states_by_symbol = defaultdict(lambda: defaultdict(list))
        for state in states:
            states_by_symbol[str(state["candidate"].get("symbol"))][
                state["strategy_type"]
            ].append(state)

        for grouped in states_by_symbol.values():
            for pair in self.allocator_v2_agreement_pairs:
                primary_states = grouped.get(pair["primary"], [])
                secondary_states = grouped.get(pair["secondary"], [])
                if not primary_states or not secondary_states:
                    continue
                for state in primary_states:
                    bonuses[state["id"]] += float(pair["primary_bonus"])
                for state in secondary_states:
                    bonuses[state["id"]] += float(pair["secondary_bonus"])

        return bonuses

    def _allocator_concentration_state(self, sleeve_name):
        default = {
            "active": False,
            "severity": 0.0,
            "budget_multiplier": 1.0,
            "priority_multiplier": 1.0,
            "leader_boost_multiplier": 1.0,
            "uniform_weight_blend": 0.0,
        }
        if (
            not self.allocator_v2_enabled
            or not self.allocator_v2_concentration_brake_enabled
        ):
            return default
        if self.daily_closed_trades < self.allocator_v2_brake_min_closed_trades:
            return default

        day_start_equity = float(self.day_start_equity or 0.0)
        realized_loss_fraction = 0.0
        if day_start_equity > 0.0 and self.daily_closed_pnl < 0.0:
            realized_loss_fraction = abs(float(self.daily_closed_pnl)) / day_start_equity

        streak_scale = 0.0
        if self.allocator_v2_brake_loss_streak_trigger > 0:
            streak_scale = min(
                1.0,
                float(self.daily_loss_streak)
                / float(self.allocator_v2_brake_loss_streak_trigger),
            )
        loss_scale = 0.0
        if self.allocator_v2_brake_daily_loss_fraction_trigger > 0.0:
            loss_scale = min(
                1.0,
                realized_loss_fraction
                / float(self.allocator_v2_brake_daily_loss_fraction_trigger),
            )
        severity = max(streak_scale, loss_scale)
        if severity <= 0.0:
            return default

        budget_floor = self.allocator_v2_brake_budget_multiplier
        priority_floor = self.allocator_v2_brake_priority_multiplier
        if str(sleeve_name or "core") == "core":
            budget_floor = min(
                budget_floor,
                self.allocator_v2_brake_core_budget_multiplier,
            )
            priority_floor = min(
                priority_floor,
                self.allocator_v2_brake_core_priority_multiplier,
            )

        return {
            "active": True,
            "severity": float(severity),
            "budget_multiplier": 1.0 - severity * (1.0 - float(budget_floor)),
            "priority_multiplier": 1.0 - severity * (1.0 - float(priority_floor)),
            "leader_boost_multiplier": 1.0
            - severity
            * (1.0 - float(self.allocator_v2_brake_leader_boost_multiplier)),
            "uniform_weight_blend": severity
            * float(self.allocator_v2_brake_uniform_weight_blend),
        }

    def _allocate_candidate_risk_fractions(self, states):
        if not states:
            return []

        agreement_bonuses = self._build_allocator_agreement_bonus_map(states)
        for state in states:
            candidate = state["candidate"]
            sleeve_name = str(state["strategy_type"] or "core")
            sleeve_cfg = self._allocator_v2_sleeve_config(sleeve_name)
            agreement_bonus = float(agreement_bonuses.get(state["id"], 0.0) or 0.0)
            coordination_priority_multiplier = float(
                state.get("coordination_priority_multiplier", 1.0) or 1.0
            )
            allocation_priority = (
                float(state["selection_score"])
                * float(sleeve_cfg.get("priority_multiplier", 1.0) or 1.0)
                * coordination_priority_multiplier
                + agreement_bonus
            )
            state["allocation_sleeve"] = sleeve_name
            state["allocation_priority"] = float(allocation_priority)
            state["leader_dominance_boost"] = 0.0
            state["agreement_bonus"] = agreement_bonus
            candidate["allocation_sleeve"] = sleeve_name
            candidate["agreement_bonus"] = agreement_bonus

        if not self.allocator_v2_enabled:
            ordered = sorted(
                states,
                key=lambda item: float(item["selection_score"]),
                reverse=True,
            )
            for rank, state in enumerate(ordered, start=1):
                state["allocation_priority"] = float(state["selection_score"])
                state["allocation_rank"] = rank
                state["allocated_risk_fraction"] = float(state["probe_risk_fraction"])
                state["candidate"]["allocation_priority"] = state["allocation_priority"]
                state["candidate"]["allocation_rank"] = rank
                state["candidate"]["allocated_risk_fraction"] = state[
                    "allocated_risk_fraction"
                ]
            return ordered

        grouped = defaultdict(list)
        for state in states:
            grouped[state["allocation_sleeve"]].append(state)

        allocated = []
        for sleeve_name, group in grouped.items():
            sleeve_cfg = self._allocator_v2_sleeve_config(sleeve_name)
            concentration_state = self._allocator_concentration_state(sleeve_name)
            ranked = sorted(
                group,
                key=lambda item: float(item["allocation_priority"]),
                reverse=True,
            )
            if (
                self.allocator_v2_leader_enabled
                and len(ranked) > 1
                and (
                    float(ranked[0]["allocation_priority"])
                    - float(ranked[1]["allocation_priority"])
                )
                >= self.allocator_v2_leader_min_gap
            ):
                gap = float(ranked[0]["allocation_priority"]) - float(
                    ranked[1]["allocation_priority"]
                )
                gap_scale = min(
                    1.0,
                    gap / max(self.allocator_v2_leader_min_gap, 1e-9),
                )
                ranked[0]["leader_dominance_boost"] = (
                    self.allocator_v2_leader_boost
                    * gap_scale
                    * float(concentration_state["leader_boost_multiplier"])
                )
                ranked[0]["allocation_priority"] *= (
                    1.0 + ranked[0]["leader_dominance_boost"]
                )
                ranked = sorted(
                    ranked,
                    key=lambda item: float(item["allocation_priority"]),
                    reverse=True,
                )

            rank_weights = list(sleeve_cfg.get("rank_weights") or [1.0])
            max_candidates = int(
                sleeve_cfg.get("max_candidates", len(rank_weights)) or len(rank_weights)
            )
            if len(rank_weights) < max_candidates:
                rank_weights.extend(
                    [rank_weights[-1]] * (max_candidates - len(rank_weights))
                )
            ranked = ranked[: max(1, max_candidates)]
            if not ranked:
                continue
            blend = float(concentration_state["uniform_weight_blend"])
            if blend > 0.0:
                rank_weights = [
                    ((1.0 - blend) * float(weight)) + blend
                    for weight in rank_weights
                ]
            raw_weights = []
            for rank_index, state in enumerate(ranked):
                rank_weight = float(rank_weights[rank_index] or 0.0)
                state["allocation_priority"] *= float(
                    concentration_state["priority_multiplier"]
                )
                state["candidate"]["allocation_brake_active"] = bool(
                    concentration_state["active"]
                )
                state["candidate"]["allocation_brake_severity"] = float(
                    concentration_state["severity"]
                )
                raw_weights.append(
                    rank_weight * max(float(state["allocation_priority"]), 0.01)
                )

            total_weight = sum(raw_weights)
            sleeve_budget = float(
                ranked[0]["strategy_sleeve_cap"]
                if float(ranked[0]["strategy_sleeve_cap"] or 0.0) > 0.0
                else self.shared_pool_risk_fraction_cap
            )
            sleeve_budget *= float(concentration_state["budget_multiplier"])
            absolute_cap = sleeve_cfg.get("absolute_max_risk_fraction")
            risk_multiplier_cap = float(
                sleeve_cfg.get("max_risk_fraction_multiplier", 1.0) or 1.0
            )
            for rank_index, state in enumerate(ranked):
                normalized_weight = (
                    raw_weights[rank_index] / total_weight if total_weight > 0.0 else 0.0
                )
                allocated_fraction = sleeve_budget * normalized_weight
                allocated_fraction = min(
                    allocated_fraction,
                    float(state["base_risk_fraction"]) * risk_multiplier_cap,
                )
                if absolute_cap not in (None, ""):
                    allocated_fraction = min(
                        allocated_fraction, float(absolute_cap or 0.0)
                    )
                state["allocation_rank"] = rank_index + 1
                state["allocated_risk_fraction"] = max(
                    0.0, float(allocated_fraction or 0.0)
                )
                state["candidate"]["allocation_priority"] = state["allocation_priority"]
                state["candidate"]["allocation_rank"] = state["allocation_rank"]
                state["candidate"]["allocated_risk_fraction"] = state[
                    "allocated_risk_fraction"
                ]
                state["candidate"]["leader_dominance_boost"] = state[
                    "leader_dominance_boost"
                ]
                state["candidate"]["allocation_brake_active"] = bool(
                    concentration_state["active"]
                )
                state["candidate"]["allocation_brake_severity"] = float(
                    concentration_state["severity"]
                )
                allocated.append(state)

        return sorted(
            allocated,
            key=lambda item: float(item["allocation_priority"]),
            reverse=True,
        )

    def _register_score_outcome(self, trade):
        score_bucket = getattr(trade, "score_bucket", None) or score_bucket_label(
            getattr(trade, "opportunity_score", 0.0) or 0.0
        )
        stats = self.score_stats[score_bucket]
        stats["count"] += 1
        stats["total_R"] += float(getattr(trade, "pnl_R_initial", 0.0) or 0.0)
        stats["total_pnl"] += float(getattr(trade, "pnl", 0.0) or 0.0)
        if float(getattr(trade, "pnl", 0.0) or 0.0) > 0:
            stats["wins"] += 1

        strategy_type = str(getattr(trade, "strategy_type", "core") or "core")
        strategy_stats = self.strategy_stats[strategy_type]
        strategy_stats["count"] += 1
        strategy_stats["total_R"] += float(getattr(trade, "pnl_R_initial", 0.0) or 0.0)
        strategy_stats["total_pnl"] += float(getattr(trade, "pnl", 0.0) or 0.0)
        if float(getattr(trade, "pnl", 0.0) or 0.0) > 0:
            strategy_stats["wins"] += 1

        feature_values = dict(getattr(trade, "feature_values", {}) or {})
        positive = float(getattr(trade, "pnl_R_initial", 0.0) or 0.0) > 0
        for feature, value in feature_values.items():
            if positive:
                self.feature_stats[feature]["sum_pos"] += float(value or 0.0)
            else:
                self.feature_stats[feature]["sum_neg"] += float(value or 0.0)
        self._record_trade_performance(trade)

    def _write_state_artifacts(self):
        if self.state_logger is None:
            return

        recent_selection_reason_counts, recent_selection_reason_counts_by_strategy = (
            self._selection_reason_counts_for_recent_window()
        )
        selection_reason_rows = self._selection_reason_summary_rows(
            self.selection_reason_counts
        )
        recent_selection_reason_rows = self._selection_reason_summary_rows(
            recent_selection_reason_counts
        )
        selection_reason_by_strategy_rows = self._selection_reason_by_strategy_rows(
            self.selection_reason_counts_by_strategy
        )
        runtime_policy_states = self._runtime_policy_states_snapshot()
        runtime_policy_rows = [
            {"strategy_type": str(strategy_type), **dict(state)}
            for strategy_type, state in runtime_policy_states.items()
        ]

        summary_rows = []
        for bucket, stats in self.score_stats.items():
            count = int(stats["count"])
            summary_rows.append(
                {
                    "bucket": bucket,
                    "count": count,
                    "win_rate": (stats["wins"] / count) if count else 0.0,
                    "avg_R": (stats["total_R"] / count) if count else 0.0,
                    "total_pnl": stats["total_pnl"],
                }
            )
        summary_rows.sort(key=lambda item: bucket_floor(item["bucket"]), reverse=True)
        self.state_logger.write_score_bucket_summary(summary_rows)
        recent_bucket_rows = []
        for bucket, stats in self.recent_score_stats.items():
            recent_bucket_rows.append(
                {
                    "bucket": bucket,
                    "count": int(stats.get("count", 0) or 0),
                    "win_rate": float(stats.get("win_rate", 0.0) or 0.0),
                    "avg_R": float(stats.get("avg_R", 0.0) or 0.0),
                    "total_pnl": float(stats.get("total_pnl", 0.0) or 0.0),
                }
            )
        recent_bucket_rows.sort(
            key=lambda item: bucket_floor(item["bucket"]),
            reverse=True,
        )
        write_recent_bucket_summary = getattr(
            self.state_logger,
            "write_recent_score_bucket_summary",
            None,
        )
        if callable(write_recent_bucket_summary):
            write_recent_bucket_summary(recent_bucket_rows)
        strategy_rows = []
        for strategy_type, stats in self.strategy_stats.items():
            count = int(stats["count"])
            strategy_rows.append(
                {
                    "strategy_type": strategy_type,
                    "count": count,
                    "win_rate": (stats["wins"] / count) if count else 0.0,
                    "avg_R": (stats["total_R"] / count) if count else 0.0,
                    "total_pnl": stats["total_pnl"],
                }
            )
        strategy_rows.sort(key=lambda item: item["total_pnl"], reverse=True)
        write_strategy_summary = getattr(self.state_logger, "write_strategy_layer_summary", None)
        if callable(write_strategy_summary):
            write_strategy_summary(strategy_rows)
        recent_strategy_rows = []
        for strategy_type, stats in self.recent_strategy_stats.items():
            multiplier, _ = self._strategy_health_multiplier(strategy_type)
            recent_strategy_rows.append(
                {
                    "strategy_type": strategy_type,
                    "count": int(stats.get("count", 0) or 0),
                    "win_rate": float(stats.get("win_rate", 0.0) or 0.0),
                    "avg_R": float(stats.get("avg_R", 0.0) or 0.0),
                    "total_pnl": float(stats.get("total_pnl", 0.0) or 0.0),
                    "risk_multiplier": float(multiplier),
                }
            )
        recent_strategy_rows.sort(
            key=lambda item: item["total_pnl"],
            reverse=True,
        )
        write_recent_strategy_summary = getattr(
            self.state_logger,
            "write_recent_strategy_layer_summary",
            None,
        )
        if callable(write_recent_strategy_summary):
            write_recent_strategy_summary(recent_strategy_rows)
        recent_strategy_bucket_rows = []
        for key, stats in self.recent_strategy_bucket_stats.items():
            strategy_type, bucket = str(key).split("|", 1)
            multiplier, source = self._strategy_bucket_health_multiplier(strategy_type, bucket)
            recent_strategy_bucket_rows.append(
                {
                    "strategy_type": strategy_type,
                    "bucket": bucket,
                    "count": int(stats.get("count", 0) or 0),
                    "win_rate": float(stats.get("win_rate", 0.0) or 0.0),
                    "avg_R": float(stats.get("avg_R", 0.0) or 0.0),
                    "total_pnl": float(stats.get("total_pnl", 0.0) or 0.0),
                    "risk_multiplier": float(multiplier),
                    "source": str(source),
                }
            )
        recent_strategy_bucket_rows.sort(
            key=lambda item: (item["strategy_type"], bucket_floor(item["bucket"])),
            reverse=True,
        )
        write_recent_strategy_bucket_summary = getattr(
            self.state_logger,
            "write_recent_strategy_bucket_summary",
            None,
        )
        if callable(write_recent_strategy_bucket_summary):
            write_recent_strategy_bucket_summary(recent_strategy_bucket_rows)
        write_daily_summary = getattr(self.state_logger, "write_daily_summary", None)
        if callable(write_daily_summary):
            write_daily_summary(list(self.daily_history))
        write_selection_reason_summary = getattr(
            self.state_logger,
            "write_selection_reason_summary",
            None,
        )
        if callable(write_selection_reason_summary):
            write_selection_reason_summary(selection_reason_rows)
        write_recent_selection_reason_summary = getattr(
            self.state_logger,
            "write_recent_selection_reason_summary",
            None,
        )
        if callable(write_recent_selection_reason_summary):
            write_recent_selection_reason_summary(recent_selection_reason_rows)
        write_selection_reason_by_strategy_summary = getattr(
            self.state_logger,
            "write_selection_reason_by_strategy_summary",
            None,
        )
        if callable(write_selection_reason_by_strategy_summary):
            write_selection_reason_by_strategy_summary(
                selection_reason_by_strategy_rows
            )
        write_runtime_policy_summary = getattr(
            self.state_logger,
            "write_runtime_policy_summary",
            None,
        )
        if callable(write_runtime_policy_summary):
            write_runtime_policy_summary(runtime_policy_rows)
        self.state_logger.write_json(
            "portfolio_status.json",
            {
                "equity": self.account.equity,
                "initial_equity": self.account.initial_equity,
                "open_positions": len(self.open_positions),
                "daily_entries_taken": self.daily_entries_taken,
                "daily_closed_trades": self.daily_closed_trades,
                "daily_closed_pnl": self.daily_closed_pnl,
                "daily_loss_streak": self.daily_loss_streak,
                "current_threshold": self.current_threshold,
                "current_threshold_floor": self.current_threshold_floor,
                "current_threshold_source": self.current_threshold_source,
                "score_weights": dict(self.scorer.weights),
                "strategy_stats": {
                    strategy_type: dict(values)
                    for strategy_type, values in self.strategy_stats.items()
                },
                "recent_score_stats": dict(self.recent_score_stats),
                "recent_strategy_stats": dict(self.recent_strategy_stats),
                "recent_score_trade_stats": dict(self.recent_score_trade_stats),
                "recent_strategy_trade_stats": dict(self.recent_strategy_trade_stats),
                "recent_strategy_bucket_stats": dict(self.recent_strategy_bucket_stats),
                "recent_strategy_bucket_trade_stats": dict(self.recent_strategy_bucket_trade_stats),
                "selection_reason_counts": {
                    str(reason): int(count or 0)
                    for reason, count in self.selection_reason_counts.items()
                },
                "recent_selection_reason_counts": {
                    str(reason): int(count or 0)
                    for reason, count in recent_selection_reason_counts.items()
                },
                "selection_reason_counts_by_strategy": {
                    str(strategy_type): {
                        str(reason): int(count or 0)
                        for reason, count in dict(reason_counts).items()
                    }
                    for strategy_type, reason_counts in self.selection_reason_counts_by_strategy.items()
                },
                "recent_selection_reason_counts_by_strategy": {
                    str(strategy_type): {
                        str(reason): int(count or 0)
                        for reason, count in dict(reason_counts).items()
                    }
                    for strategy_type, reason_counts in recent_selection_reason_counts_by_strategy.items()
                },
                "cap_pressure_summary": {
                    "cumulative": self._cap_pressure_summary_from_counts(
                        self.selection_reason_counts
                    ),
                    "recent": self._cap_pressure_summary_from_counts(
                        recent_selection_reason_counts
                    ),
                },
                "runtime_policy_states": runtime_policy_states,
                "top_symbols": list(self.last_top_symbols),
            },
        )

    def flush_state(self):
        self._write_state_artifacts()

    def finalize_backtest(self, latest_rows_by_symbol=None, *, close_open_positions=True):
        latest_rows_by_symbol = dict(latest_rows_by_symbol or {})

        if close_open_positions:
            for trade in list(self.open_positions):
                row = latest_rows_by_symbol.get(getattr(trade, "symbol", None))
                if row is None:
                    continue
                self.close_trade(trade, row, reason="end_of_replay")

        self._record_completed_day()
        self.current_trading_day = None
        self._write_state_artifacts()

    def summary(self):
        self.account.summary()
        completed_days = len(self.daily_history)
        if completed_days <= 0:
            return

        total_entries = sum(int(row.get("entries_taken", 0) or 0) for row in self.daily_history)
        total_realized_pnl = sum(
            float(row.get("realized_pnl", 0.0) or 0.0)
            for row in self.daily_history
        )
        avg_entries = total_entries / completed_days if completed_days else 0.0
        avg_daily_pnl = total_realized_pnl / completed_days if completed_days else 0.0

        print("\nPORTFOLIO DAILY SUMMARY")
        print(f"  Days tracked: {completed_days}")
        print(f"  Avg entries/day: {avg_entries:.2f}")
        print(f"  Avg realized PnL/day: {avg_daily_pnl:.2f}")
        print(f"  Current threshold: {self.current_threshold:.2f}")

    def snapshot_state(self):
        return {
            "account": self.account.snapshot(),
            "current_threshold": self.current_threshold,
            "score_weights": dict(self.scorer.weights),
            "current_threshold_floor": self.current_threshold_floor,
            "current_threshold_source": self.current_threshold_source,
            "current_trading_day": (
                None if self.current_trading_day is None else str(self.current_trading_day)
            ),
            "day_start_equity": self.day_start_equity,
            "daily_entries_taken": self.daily_entries_taken,
            "daily_closed_trades": self.daily_closed_trades,
            "daily_closed_pnl": self.daily_closed_pnl,
            "daily_loss_streak": self.daily_loss_streak,
            "daily_history": [
                {
                    **dict(row),
                    "date": str(row.get("date")) if row.get("date") is not None else None,
                }
                for row in self.daily_history
            ],
            "score_stats": {
                bucket: dict(values)
                for bucket, values in self.score_stats.items()
            },
            "strategy_stats": {
                strategy_type: dict(values)
                for strategy_type, values in self.strategy_stats.items()
            },
            "feature_stats": {
                feature: dict(values)
                for feature, values in self.feature_stats.items()
            },
            "performance_history": [
                {
                    **dict(record),
                    "exit_time": (
                        None
                        if record.get("exit_time") is None
                        else record.get("exit_time").isoformat()
                    ),
                }
                for record in self.performance_history
            ],
            "recent_score_trade_stats": dict(self.recent_score_trade_stats),
            "recent_strategy_trade_stats": dict(self.recent_strategy_trade_stats),
            "recent_strategy_bucket_stats": dict(self.recent_strategy_bucket_stats),
            "recent_strategy_bucket_trade_stats": dict(self.recent_strategy_bucket_trade_stats),
            "selection_reason_counts": {
                str(reason): int(count or 0)
                for reason, count in self.selection_reason_counts.items()
            },
            "selection_reason_counts_by_strategy": {
                str(strategy_type): {
                    str(reason): int(count or 0)
                    for reason, count in dict(reason_counts).items()
                }
                for strategy_type, reason_counts in self.selection_reason_counts_by_strategy.items()
            },
            "selection_reason_history": [
                {
                    **dict(record),
                    "timestamp": (
                        None
                        if record.get("timestamp") is None
                        else record.get("timestamp").isoformat()
                    ),
                }
                for record in self.selection_reason_history
            ],
            "last_top_symbols": list(self.last_top_symbols),
            "open_positions": [
                trade.snapshot()
                for trade in self.open_positions
            ],
        }

    def restore_state(self, snapshot):
        if not snapshot:
            return

        account_snapshot = snapshot.get("account")
        if account_snapshot:
            self.account.restore(account_snapshot)

        self.current_threshold = float(
            snapshot.get("current_threshold", self.current_threshold)
        )
        self.current_threshold_floor = float(
            snapshot.get("current_threshold_floor", self.current_threshold_floor)
        )
        self.current_threshold_source = str(
            snapshot.get("current_threshold_source", self.current_threshold_source)
        )
        raw_weights = snapshot.get("score_weights") or {}
        if raw_weights:
            self.scorer.weights.update(
                {
                    key: float(value)
                    for key, value in raw_weights.items()
                    if key in self.scorer.weights
                }
            )
        current_trading_day = snapshot.get("current_trading_day")
        if current_trading_day:
            self.current_trading_day = datetime.fromisoformat(
                str(current_trading_day)
            ).date()
        else:
            self.current_trading_day = None
        self.day_start_equity = float(
            snapshot.get("day_start_equity", self.day_start_equity)
        )
        self.daily_entries_taken = int(
            snapshot.get("daily_entries_taken", self.daily_entries_taken)
        )
        self.daily_closed_trades = int(
            snapshot.get("daily_closed_trades", self.daily_closed_trades)
        )
        self.daily_closed_pnl = float(
            snapshot.get("daily_closed_pnl", self.daily_closed_pnl)
        )
        self.daily_loss_streak = int(
            snapshot.get("daily_loss_streak", self.daily_loss_streak)
        )
        self.daily_history = [
            {
                **dict(row),
                "date": (
                    None
                    if row.get("date") in (None, "")
                    else datetime.fromisoformat(str(row.get("date"))).date()
                ),
            }
            for row in (snapshot.get("daily_history") or [])
        ]
        self.score_stats = defaultdict(
            lambda: {"count": 0, "wins": 0, "total_R": 0.0, "total_pnl": 0.0}
        )
        for bucket, values in (snapshot.get("score_stats") or {}).items():
            self.score_stats[str(bucket)] = {
                "count": int(values.get("count", 0) or 0),
                "wins": int(values.get("wins", 0) or 0),
                "total_R": float(values.get("total_R", 0.0) or 0.0),
                "total_pnl": float(values.get("total_pnl", 0.0) or 0.0),
            }
        self.strategy_stats = defaultdict(
            lambda: {"count": 0, "wins": 0, "total_R": 0.0, "total_pnl": 0.0}
        )
        for strategy_type, values in (snapshot.get("strategy_stats") or {}).items():
            self.strategy_stats[str(strategy_type)] = {
                "count": int(values.get("count", 0) or 0),
                "wins": int(values.get("wins", 0) or 0),
                "total_R": float(values.get("total_R", 0.0) or 0.0),
                "total_pnl": float(values.get("total_pnl", 0.0) or 0.0),
            }
        self.feature_stats = defaultdict(
            lambda: {"sum_pos": 0.0, "sum_neg": 0.0}
        )
        for feature, values in (snapshot.get("feature_stats") or {}).items():
            self.feature_stats[str(feature)] = {
                "sum_pos": float(values.get("sum_pos", 0.0) or 0.0),
                "sum_neg": float(values.get("sum_neg", 0.0) or 0.0),
            }
        self.performance_history = [
            {
                **dict(record),
                "exit_time": self._normalize_time_value(record.get("exit_time")),
            }
            for record in (snapshot.get("performance_history") or [])
        ]
        self._trim_performance_history()
        self._refresh_recent_performance()
        recent_score_trade_stats = snapshot.get("recent_score_trade_stats") or {}
        if recent_score_trade_stats:
            self.recent_score_trade_stats = {
                str(bucket): {
                    "count": int(values.get("count", 0) or 0),
                    "wins": int(values.get("wins", 0) or 0),
                    "total_R": float(values.get("total_R", 0.0) or 0.0),
                    "total_pnl": float(values.get("total_pnl", 0.0) or 0.0),
                    "avg_R": float(values.get("avg_R", 0.0) or 0.0),
                    "win_rate": float(values.get("win_rate", 0.0) or 0.0),
                }
                for bucket, values in recent_score_trade_stats.items()
            }
        recent_strategy_trade_stats = snapshot.get("recent_strategy_trade_stats") or {}
        if recent_strategy_trade_stats:
            self.recent_strategy_trade_stats = {
                str(strategy_type): {
                    "count": int(values.get("count", 0) or 0),
                    "wins": int(values.get("wins", 0) or 0),
                    "total_R": float(values.get("total_R", 0.0) or 0.0),
                    "total_pnl": float(values.get("total_pnl", 0.0) or 0.0),
                    "avg_R": float(values.get("avg_R", 0.0) or 0.0),
                    "win_rate": float(values.get("win_rate", 0.0) or 0.0),
                }
                for strategy_type, values in recent_strategy_trade_stats.items()
            }
        recent_strategy_bucket_stats = snapshot.get("recent_strategy_bucket_stats") or {}
        if recent_strategy_bucket_stats:
            self.recent_strategy_bucket_stats = {
                str(key): {
                    "count": int(values.get("count", 0) or 0),
                    "wins": int(values.get("wins", 0) or 0),
                    "total_R": float(values.get("total_R", 0.0) or 0.0),
                    "total_pnl": float(values.get("total_pnl", 0.0) or 0.0),
                    "avg_R": float(values.get("avg_R", 0.0) or 0.0),
                    "win_rate": float(values.get("win_rate", 0.0) or 0.0),
                }
                for key, values in recent_strategy_bucket_stats.items()
            }
        recent_strategy_bucket_trade_stats = snapshot.get("recent_strategy_bucket_trade_stats") or {}
        if recent_strategy_bucket_trade_stats:
            self.recent_strategy_bucket_trade_stats = {
                str(key): {
                    "count": int(values.get("count", 0) or 0),
                    "wins": int(values.get("wins", 0) or 0),
                    "total_R": float(values.get("total_R", 0.0) or 0.0),
                    "total_pnl": float(values.get("total_pnl", 0.0) or 0.0),
                    "avg_R": float(values.get("avg_R", 0.0) or 0.0),
                    "win_rate": float(values.get("win_rate", 0.0) or 0.0),
                }
                for key, values in recent_strategy_bucket_trade_stats.items()
            }
        self.selection_reason_counts = defaultdict(int)
        for reason, count in (snapshot.get("selection_reason_counts") or {}).items():
            self.selection_reason_counts[str(reason)] = int(count or 0)
        self.selection_reason_counts_by_strategy = defaultdict(
            lambda: defaultdict(int)
        )
        for strategy_type, reason_counts in (
            snapshot.get("selection_reason_counts_by_strategy") or {}
        ).items():
            nested = defaultdict(int)
            for reason, count in dict(reason_counts or {}).items():
                nested[str(reason)] = int(count or 0)
            self.selection_reason_counts_by_strategy[str(strategy_type)] = nested
        self.selection_reason_history = [
            {
                **dict(record),
                "timestamp": self._normalize_time_value(record.get("timestamp")),
            }
            for record in (snapshot.get("selection_reason_history") or [])
        ]
        self._trim_selection_reason_history()
        self.last_top_symbols = list(snapshot.get("last_top_symbols") or [])
        self.open_positions = [
            Trade.from_snapshot(trade_snapshot, config=self.config)
            for trade_snapshot in (snapshot.get("open_positions") or [])
        ]

    def close_trade(self, trade, row, *, reason, exit_price=None):
        trade.annotate_exit(reason=reason)
        trade.close(row, exit_price=exit_price)
        self.account.update(trade)
        self.daily_closed_trades += 1
        realized_pnl = float(getattr(trade, "pnl", 0.0) or 0.0)
        self.daily_closed_pnl += realized_pnl
        if realized_pnl > 0.0:
            self.daily_loss_streak = 0
        else:
            self.daily_loss_streak += 1
        self._register_score_outcome(trade)
        if self.trade_logger is not None:
            self.trade_logger.log_trade(trade)
        if trade in self.open_positions:
            self.open_positions.remove(trade)
        self._write_state_artifacts()

    def manage_open_positions(self, latest_rows_by_symbol, htf_context_by_symbol=None):
        if not self.open_positions:
            return

        htf_context_by_symbol = htf_context_by_symbol or {}
        state_changed = False
        for trade in list(self.open_positions):
            symbol = getattr(trade, "symbol", None)
            row = latest_rows_by_symbol.get(symbol)
            if row is None:
                continue

            trade.advance_bar()
            if self._is_htf_strategy_type(getattr(trade, "strategy_type", "core")):
                if self._manage_htf_trade(trade, row, htf_context_by_symbol.get(symbol) or {}):
                    continue

                state_changed = True
                if self._maybe_apply_convexity(
                    trade,
                    row,
                    open_r_multiple=self._open_r_multiple(trade, float(row["close"])),
                ):
                    state_changed = True
                continue

            active_stop = float(getattr(trade, "active_stop", trade.stop))
            if self.exit_engine.should_exit(row, active_stop, side=trade.side):
                exit_reason = "trailing stop" if active_stop != trade.stop else "hard exit"
                self.close_trade(trade, row, reason=exit_reason, exit_price=active_stop)
                continue

            open_r_multiple = self._open_r_multiple(trade, float(row["close"]))
            trailing_activation_r = float(
                getattr(trade, "trailing_activation_r", None)
                or self.trailing_activation_r
            )
            slow_grind_max_bars = int(
                getattr(trade, "slow_grind_max_bars", None)
                or self.slow_grind_max_bars
            )
            slow_grind_open_r_max = float(
                getattr(trade, "slow_grind_open_r_max", None)
                or self.slow_grind_open_r_max
            )

            if getattr(trade, "max_hold_candles", None) is not None and int(
                getattr(trade, "bars_held", 0) or 0
            ) >= int(trade.max_hold_candles):
                self.close_trade(trade, row, reason="time exit")
                continue

            profit_lock_trigger_r = getattr(trade, "profit_lock_trigger_r", None)
            profit_lock_stop_r = getattr(trade, "profit_lock_stop_r", None)
            if (
                profit_lock_trigger_r is not None
                and profit_lock_stop_r is not None
                and open_r_multiple >= float(profit_lock_trigger_r)
            ):
                locked_stop = float(trade.entry_price) + (
                    float(profit_lock_stop_r) * float(trade.R)
                )
                if trade.side == "short":
                    locked_stop = float(trade.entry_price) - (
                        float(profit_lock_stop_r) * float(trade.R)
                    )
                    trade.active_stop = min(float(trade.active_stop), locked_stop)
                else:
                    trade.active_stop = max(float(trade.active_stop), locked_stop)

            if open_r_multiple >= self.breakeven_trigger_r:
                if trade.side == "short":
                    trade.active_stop = min(float(trade.active_stop), float(trade.entry_price))
                else:
                    trade.active_stop = max(float(trade.active_stop), float(trade.entry_price))

            if self._maybe_apply_convexity(
                trade,
                row,
                open_r_multiple=open_r_multiple,
            ):
                state_changed = True

            if (
                getattr(trade, "convexity_enabled", False)
                and int(getattr(trade, "convexity_stage", 0) or 0) > 0
                and self._convexity_trend_supports_hold(row, trade.side)
            ):
                slow_grind_max_bars += self.convexity_hold_extension_bars

            if (
                slow_grind_max_bars > 0
                and int(getattr(trade, "bars_held", 0) or 0) >= slow_grind_max_bars
                and open_r_multiple < slow_grind_open_r_max
            ):
                self.close_trade(trade, row, reason="slow grind exit")
                continue

            if getattr(trade, "disable_trailing", False):
                continue
            if open_r_multiple < trailing_activation_r:
                continue

            result = self.trend_sniffer.evaluate(row, trade=trade)
            trade.update_trailing_state(
                trail_state=result["state"],
                anchor_column=result["anchor_column"],
                anchor_price=result["anchor_price"],
                open_r_multiple=result["open_r_multiple"],
                momentum_score=result["momentum_score"],
                decay_score=result["decay_score"],
                proposed_stop=(None if result["should_exit"] else result["proposed_stop"]),
            )
            if result["should_exit"]:
                exit_reason = "state exit" if result["state"] == "exit" else "trend weakness"
                self.close_trade(trade, row, reason=exit_reason)
        if state_changed:
            self._write_state_artifacts()

    def select_and_open(self, candidates, timestamp):
        self.last_top_symbols = [
            candidate["symbol"] for candidate in sorted(
                candidates,
                key=lambda item: float(item.get("momentum_rank", 0.0)),
                reverse=True,
            )[:3]
        ]
        states = [
            self._build_candidate_selection_state(candidate, timestamp, candidate_id=index)
            for index, candidate in enumerate(candidates)
        ]
        eligible_states = [state for state in states if state["reason"] is None]
        ordered_states = self._allocate_candidate_risk_fractions(eligible_states)
        allocated_state_ids = {state["id"] for state in ordered_states}
        final_reason_by_id = {
            state["id"]: str(state["reason"])
            for state in states
            if state["reason"] is not None
        }
        opened_this_step = 0
        opened_by_strategy = defaultdict(int)

        for state in ordered_states:
            candidate = state["candidate"]
            state_id = state["id"]
            strategy_type = state["strategy_type"]
            risk_group = state["risk_group"]
            group_risk_cap = state["group_risk_cap"]
            strategy_sleeve_cap = float(state["strategy_sleeve_cap"] or 0.0)
            strategy_step_cap = state["strategy_step_cap"]
            ignore_global_step_cap = bool(state["ignore_global_step_cap"])
            if state["allocated_risk_fraction"] <= 0.0:
                final_reason_by_id[state_id] = "allocator_zero_risk"
                continue
            if self.daily_entries_taken >= self.max_trades_per_day:
                final_reason_by_id[state_id] = "daily_trade_cap"
                continue
            if (
                strategy_step_cap not in (None, "")
                and opened_by_strategy[strategy_type] >= int(strategy_step_cap)
            ):
                final_reason_by_id[state_id] = "strategy_step_cap"
                continue
            if (
                not ignore_global_step_cap
                and opened_this_step >= self.max_new_positions_per_step
            ):
                final_reason_by_id[state_id] = "step_position_cap"
                continue

            risk_fraction = float(state["allocated_risk_fraction"])
            projected_total_risk = self._active_risk_fraction() + risk_fraction
            projected_group_risk = (
                self._active_risk_fraction(risk_group=risk_group) + risk_fraction
                if risk_group and group_risk_cap not in (None, "")
                else None
            )
            projected_strategy_risk = (
                self._active_strategy_risk_fraction(strategy_type) + risk_fraction
            )
            projected_shared_risk = self._active_shared_risk_fraction() + risk_fraction
            if (
                strategy_sleeve_cap > 0.0
                and projected_total_risk > self.max_total_risk_fraction
            ):
                final_reason_by_id[state_id] = "risk_cap"
                continue
            if (
                strategy_sleeve_cap > 0.0
                and projected_strategy_risk > strategy_sleeve_cap
            ):
                final_reason_by_id[state_id] = "strategy_sleeve_cap"
                continue
            if (
                strategy_sleeve_cap <= 0.0
                and self.total_reserved_sleeve_risk_fraction > 0.0
                and projected_shared_risk > self.shared_pool_risk_fraction_cap
            ):
                final_reason_by_id[state_id] = "shared_risk_cap"
                continue
            if projected_total_risk > self.max_total_risk_fraction:
                final_reason_by_id[state_id] = "risk_cap"
                continue
            if (
                projected_group_risk is not None
                and projected_group_risk > float(group_risk_cap)
            ):
                final_reason_by_id[state_id] = "strategy_risk_cap"
                continue

            row = candidate["row"]
            trade = Trade(
                row=row,
                score=state["score"],
                side=candidate["side"],
                config=self.config,
            )
            stop_price = float(
                candidate.get("stop_price_override", trade.stop) or trade.stop
            )
            size = self.position_sizer.calculate(
                equity=self.account.equity,
                risk_per_trade=risk_fraction,
                entry_price=row["close"],
                stop_price=stop_price,
            )
            if size <= 0:
                final_reason_by_id[state_id] = "invalid_size"
                continue

            if candidate.get("stop_price_override") not in (None, ""):
                trade.stop = stop_price
                trade.active_stop = stop_price
                trade.R = abs(float(trade.entry_price) - float(stop_price))
            trade.annotate_live_scoring(
                symbol=candidate["symbol"],
                opportunity_score=state["score"],
                score_bucket=candidate.get("score_bucket"),
                momentum_rank=candidate.get("momentum_rank"),
                feature_values=candidate.get("feature_values"),
                strategy_type=candidate.get("strategy_type"),
                risk_group=candidate.get("risk_group"),
                selection_score=state["selection_score"],
                moonshot_score=candidate.get("moonshot_score"),
                range_expansion_factor=candidate.get("range_expansion_factor"),
            )
            trade.annotate_signal_family(
                candidate.get("signal_family", "live_paper"),
                pressure_score=None,
            )
            trade.annotate_edge_bucket(
                edge_type=candidate.get("edge_type"),
                body_bucket=candidate.get("body_bucket"),
                vwap_bucket=candidate.get("vwap_bucket"),
                bucket_key=candidate.get("bucket_key_text"),
                bucket_expected_return=candidate.get("bucket_expected_return"),
                bucket_risk_mult=candidate.get("bucket_risk_mult"),
            )
            trade.annotate_weighted_context(
                score_norm=state["score"],
                momentum_strength=candidate.get("momentum_rank"),
                final_strength=state["score"],
                bias_weight=None,
                regime_weight=None,
                event_bonus=None,
            )
            trade.annotate_entry_context(
                bias=candidate.get("bias"),
                regime_score=None,
                regime_class=None,
                entry_threshold=state["threshold"],
            )
            trade.annotate_risk_context(
                equity_at_entry=self.account.equity,
                entry_risk_multiplier=candidate.get("risk_mult", 1.0),
                runtime_risk_multiplier=float(
                    candidate.get("bucket_health_mult", 1.0)
                )
                * float(candidate.get("strategy_health_mult", 1.0)),
                intended_risk_per_trade=state["base_risk_fraction"],
                effective_risk_fraction=risk_fraction,
            )
            trade.annotate_edge_execution_profile(
                **dict(candidate.get("execution_profile") or {})
            )
            if candidate.get("htf_signal_family") is not None:
                trade.annotate_htf_context(
                    signal_family=candidate.get("htf_signal_family"),
                    htf_score=candidate.get("htf_score"),
                    context_1d=candidate.get("htf_context_1d"),
                    context_1w=candidate.get("htf_context_1w"),
                    entry_reason=candidate.get("htf_entry_reason"),
                    stop_reason=candidate.get("htf_stop_reason"),
                    trailing_state=candidate.get("htf_trailing_state"),
                    decay_reason=candidate.get("htf_decay_reason"),
                    candidate_rank=candidate.get("htf_candidate_rank"),
                )
            trade.add_entry(row["close"], size)
            trade.conditions["group_risk_cap"] = group_risk_cap
            trade.conditions["strategy_sleeve_cap"] = strategy_sleeve_cap
            trade.conditions["allocation_sleeve"] = candidate.get("allocation_sleeve")
            trade.conditions["allocation_rank"] = candidate.get("allocation_rank")
            trade.conditions["allocation_priority"] = candidate.get(
                "allocation_priority"
            )
            trade.conditions["coordination_active"] = bool(
                candidate.get("coordination_active")
            )
            trade.conditions["coordination_rule"] = candidate.get("coordination_rule")
            trade.conditions["coordination_context_1d"] = candidate.get(
                "coordination_context_1d"
            )
            trade.conditions["coordination_priority_multiplier"] = candidate.get(
                "coordination_priority_multiplier"
            )
            trade.conditions["coordination_base_risk_multiplier"] = candidate.get(
                "coordination_base_risk_multiplier"
            )
            trade.conditions["coordination_sleeve_cap_multiplier"] = candidate.get(
                "coordination_sleeve_cap_multiplier"
            )
            if (
                strategy_sleeve_cap <= 0.0
                and self.total_reserved_sleeve_risk_fraction > 0.0
            ):
                trade.conditions["shared_pool_cap"] = self.shared_pool_risk_fraction_cap
            if state["convexity_enabled"]:
                base_risk_amount = float(trade.equity_at_entry or 0.0) * float(
                    state["base_risk_fraction"]
                )
                trade.initial_risk_amount = base_risk_amount
                trade.annotate_convexity_profile(
                    enabled=True,
                    state="probe",
                    stage=0,
                    base_risk_fraction=state["base_risk_fraction"],
                    probe_fraction=self.convexity_probe_fraction,
                    target_risk_fraction=state["base_risk_fraction"],
                    base_risk_amount=base_risk_amount,
                    promote_target_multiple=self.convexity_promote_target_multiple,
                    add_target_multiple=self.convexity_add_target_multiple,
                    max_target_multiple=self.convexity_max_target_multiple,
                    add_count=0,
                    last_add_bar=0,
                )
            self.open_positions.append(trade)
            self.daily_entries_taken += 1
            opened_this_step += 1
            opened_by_strategy[strategy_type] += 1
            final_reason_by_id[state_id] = "opened"

        for state in states:
            candidate = state["candidate"]
            reason = final_reason_by_id.get(state["id"])
            if reason is None:
                if state["id"] in allocated_state_ids:
                    reason = "allocator_not_selected"
                else:
                    reason = "allocator_rank_filtered"
            final_reason_by_id[state["id"]] = reason
            if self.signal_logger is not None:
                self.signal_logger.log_signal(
                    self.build_signal_log_row(
                        candidate,
                        threshold=state["threshold"],
                        selected=(reason == "opened"),
                        selection_reason=reason,
                    )
                )

        self._record_selection_decisions(states, final_reason_by_id, timestamp)
        self._write_state_artifacts()
