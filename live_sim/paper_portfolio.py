"""Lean multi-asset live paper portfolio with adaptive score-based selection."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

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

        self.current_trading_day = None
        self.day_start_equity = self.account.equity
        self.daily_entries_taken = 0
        self.daily_closed_trades = 0
        self.daily_closed_pnl = 0.0
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
        self.last_top_symbols = []

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

    def _active_risk_fraction(self, risk_group=None):
        equity = float(self.account.equity or 0.0)
        if equity <= 0:
            return 0.0
        total = 0.0
        for trade in self.open_positions:
            if risk_group and getattr(trade, "risk_group", None) != risk_group:
                continue
            total += abs(float(trade.entry_price) - float(trade.stop)) * sum(
                float(size) for _, size in trade.entries
            )
        return total / equity

    def _asset_open_count(self, symbol):
        return sum(1 for trade in self.open_positions if getattr(trade, "symbol", None) == symbol)

    def _direction_open_count(self, side):
        return sum(1 for trade in self.open_positions if getattr(trade, "side", None) == side)

    def _elapsed_day_fraction(self, timestamp):
        seconds = (
            timestamp.hour * 3600
            + timestamp.minute * 60
            + timestamp.second
        )
        return clamp(seconds / float(24 * 3600))

    def _derive_threshold_from_history(self):
        profitable_floors = []
        for bucket, stats in self.score_stats.items():
            count = int(stats["count"])
            if count < self.min_profitable_bucket_count:
                continue
            avg_r = float(stats["total_R"]) / count
            if avg_r > 0:
                profitable_floors.append(bucket_floor(bucket))

        if not profitable_floors:
            return self.base_threshold

        return min(profitable_floors)

    def _update_threshold_for_new_day(self):
        derived = self._derive_threshold_from_history()
        if self.current_trading_day is not None:
            if self.daily_entries_taken < self.min_trades_per_day:
                derived -= self.pacing_relax_step
            elif self.daily_entries_taken > self.max_trades_per_day:
                derived += self.pacing_tighten_step
        derived = clamp(derived, self.min_threshold, self.max_threshold)
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
            "threshold": threshold,
            "selected": selected,
            "selection_reason": selection_reason,
            "bucket_valid": candidate.get("bucket_valid"),
            "bucket_expected_return": candidate.get("bucket_expected_return"),
            "bucket_risk_mult": candidate.get("bucket_risk_mult"),
        }

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

    def _write_state_artifacts(self):
        if self.state_logger is None:
            return

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
        write_daily_summary = getattr(self.state_logger, "write_daily_summary", None)
        if callable(write_daily_summary):
            write_daily_summary(list(self.daily_history))
        self.state_logger.write_json(
            "portfolio_status.json",
            {
                "equity": self.account.equity,
                "initial_equity": self.account.initial_equity,
                "open_positions": len(self.open_positions),
                "daily_entries_taken": self.daily_entries_taken,
                "daily_closed_trades": self.daily_closed_trades,
                "daily_closed_pnl": self.daily_closed_pnl,
                "current_threshold": self.current_threshold,
                "score_weights": dict(self.scorer.weights),
                "strategy_stats": {
                    strategy_type: dict(values)
                    for strategy_type, values in self.strategy_stats.items()
                },
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
            "current_trading_day": (
                None if self.current_trading_day is None else str(self.current_trading_day)
            ),
            "day_start_equity": self.day_start_equity,
            "daily_entries_taken": self.daily_entries_taken,
            "daily_closed_trades": self.daily_closed_trades,
            "daily_closed_pnl": self.daily_closed_pnl,
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
        self.daily_closed_pnl += float(getattr(trade, "pnl", 0.0) or 0.0)
        self._register_score_outcome(trade)
        if self.trade_logger is not None:
            self.trade_logger.log_trade(trade)
        if trade in self.open_positions:
            self.open_positions.remove(trade)
        self._write_state_artifacts()

    def manage_open_positions(self, latest_rows_by_symbol):
        if not self.open_positions:
            return

        for trade in list(self.open_positions):
            symbol = getattr(trade, "symbol", None)
            row = latest_rows_by_symbol.get(symbol)
            if row is None:
                continue

            trade.advance_bar()
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

    def select_and_open(self, candidates, timestamp):
        threshold = self.adaptive_threshold(timestamp)
        self.last_top_symbols = [
            candidate["symbol"] for candidate in sorted(
                candidates,
                key=lambda item: float(item.get("momentum_rank", 0.0)),
                reverse=True,
            )[:3]
        ]

        ordered = sorted(
            candidates,
            key=lambda item: float(item.get("selection_score", item.get("score", 0.0))),
            reverse=True,
        )
        opened_this_step = 0

        for candidate in ordered:
            reason = "score_below_threshold"
            selected = False
            score = float(candidate.get("score", 0.0) or 0.0)
            selection_score = float(
                candidate.get("selection_score", candidate.get("score", 0.0)) or 0.0
            )
            score_bucket = candidate.get("score_bucket")
            score_bucket_risk_mult = self._score_bucket_risk_multiplier(score_bucket)
            risk_group = candidate.get("risk_group")
            group_risk_cap = candidate.get("group_risk_cap")

            if candidate.get("side") not in self.allowed_sides:
                reason = "side_disabled"
            elif score_bucket_risk_mult <= 0.0:
                reason = "score_bucket_filtered"
            elif selection_score < threshold:
                reason = "score_below_threshold"
            elif opened_this_step >= self.max_new_positions_per_step:
                reason = "step_position_cap"
            elif self._asset_open_count(candidate["symbol"]) >= self.max_trades_per_asset:
                reason = "asset_cap"
            elif self._direction_open_count(candidate["side"]) >= self.max_same_direction_positions:
                reason = "direction_cap"
            else:
                if candidate.get("risk_fraction_override") not in (None, ""):
                    risk_fraction = float(candidate.get("risk_fraction_override"))
                else:
                    risk_fraction = self._risk_fraction_for_score(
                        score,
                        risk_mult=(
                            float(candidate.get("risk_mult", 1.0) or 1.0)
                            * score_bucket_risk_mult
                        ),
                    )
                projected_total_risk = self._active_risk_fraction() + risk_fraction
                if projected_total_risk > self.max_total_risk_fraction:
                    reason = "risk_cap"
                elif (
                    risk_group
                    and group_risk_cap not in (None, "")
                    and (self._active_risk_fraction(risk_group=risk_group) + risk_fraction)
                    > float(group_risk_cap)
                ):
                    reason = "strategy_risk_cap"
                else:
                    row = candidate["row"]
                    trade = Trade(
                        row=row,
                        score=score,
                        side=candidate["side"],
                        config=self.config,
                    )
                    size = self.position_sizer.calculate(
                        equity=self.account.equity,
                        risk_per_trade=risk_fraction,
                        entry_price=row["close"],
                        stop_price=trade.stop,
                    )
                    if size <= 0:
                        reason = "invalid_size"
                    else:
                        trade.annotate_live_scoring(
                            symbol=candidate["symbol"],
                            opportunity_score=score,
                            score_bucket=candidate.get("score_bucket"),
                            momentum_rank=candidate.get("momentum_rank"),
                            feature_values=candidate.get("feature_values"),
                            strategy_type=candidate.get("strategy_type"),
                            risk_group=candidate.get("risk_group"),
                            selection_score=selection_score,
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
                            score_norm=score,
                            momentum_strength=candidate.get("momentum_rank"),
                            final_strength=score,
                            bias_weight=None,
                            regime_weight=None,
                            event_bonus=None,
                        )
                        trade.annotate_entry_context(
                            bias=candidate.get("bias"),
                            regime_score=None,
                            regime_class=None,
                            entry_threshold=threshold,
                        )
                        trade.annotate_risk_context(
                            equity_at_entry=self.account.equity,
                            entry_risk_multiplier=candidate.get("risk_mult", 1.0),
                            runtime_risk_multiplier=1.0,
                            intended_risk_per_trade=risk_fraction,
                            effective_risk_fraction=risk_fraction,
                        )
                        trade.annotate_edge_execution_profile(
                            **dict(candidate.get("execution_profile") or {})
                        )
                        trade.add_entry(row["close"], size)
                        self.open_positions.append(trade)
                        self.daily_entries_taken += 1
                        opened_this_step += 1
                        selected = True
                        reason = "opened"

            if self.signal_logger is not None:
                self.signal_logger.log_signal(
                    self.build_signal_log_row(
                        candidate,
                        threshold=threshold,
                        selected=selected,
                        selection_reason=reason,
                    )
                )

            if self.daily_entries_taken >= self.max_trades_per_day:
                break

        self._write_state_artifacts()
