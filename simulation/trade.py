"""Represents the full lifecycle of one trade, including entries, exits, and PnL."""

import time
from datetime import datetime

from common.debug import debug_print as print
from config import AppConfig


TRADE_LOG_FIELDS = [
    "trade_id",
    "opportunity_id",
    "symbol",
    "side",
    "request_type",
    "capital_lane",
    "lineage_id",
    "lineage_parent_trade_id",
    "lineage_reentry_count",
    "signal_family",
    "edge_type",
    "body_bucket",
    "vwap_bucket",
    "edge_bucket_key",
    "bucket_expected_return",
    "bucket_risk_mult",
    "entry_time",
    "exit_time",
    "entry_price",
    "exit_price",
    "stop_price",
    "active_stop_price",
    "pnl",
    "pnl_R",
    "pnl_R_total",
    "pnl_R_initial",
    "initial_risk_amount",
    "total_risk_amount",
    "equity_at_entry",
    "entry_risk_multiplier",
    "runtime_risk_multiplier",
    "intended_risk_per_trade",
    "effective_risk_fraction",
    "equity_return_fraction",
    "bias",
    "regime_score",
    "regime_class",
    "entry_threshold",
    "exit_reason",
    "lifecycle_state",
    "lifecycle_detail",
    "lifecycle_updated_at",
    "pressure_score",
    "opportunity_score",
    "score_bucket",
    "momentum_rank",
    "strategy_type",
    "risk_group",
    "selection_score",
    "moonshot_score",
    "range_expansion_factor",
    "score_norm",
    "momentum_strength",
    "final_strength",
    "bias_weight",
    "regime_weight",
    "event_bonus",
    "trail_state",
    "trail_anchor_column",
    "trail_anchor_price",
    "trail_open_r_multiple",
    "trail_momentum_score",
    "trail_decay_score",
    "bars_held",
    "max_hold_candles",
    "trailing_activation_r",
    "slow_grind_max_bars",
    "slow_grind_open_r_max",
    "entry_layer_count",
    "pyramid_level",
    "convexity_enabled",
    "convexity_state",
    "convexity_stage",
    "convexity_base_risk_fraction",
    "convexity_probe_fraction",
    "convexity_target_risk_fraction",
    "convexity_base_risk_amount",
    "convexity_promote_target_multiple",
    "convexity_add_target_multiple",
    "convexity_max_target_multiple",
    "convexity_add_count",
    "convexity_last_add_bar",
    "htf_signal_family",
    "htf_score",
    "htf_context_1d",
    "htf_context_1w",
    "htf_entry_reason",
    "htf_stop_reason",
    "htf_trailing_state",
    "htf_decay_reason",
    "htf_candidate_rank",
    "score",
    "body_strength",
    "close_position",
    "upper_wick_ratio",
    "lower_wick_ratio",
    "compression",
    "breakout",
    "breakdown",
    "session_vwap",
    "vwap_distance_ratio",
    "ema_gap_ratio",
    "atr",
    "macd_hist",
]


def trade_to_log_record(trade):
    conditions = getattr(trade, "conditions", {}) or {}
    entries = getattr(trade, "entries", None)
    if entries is not None:
        entry_layer_count = len(entries)
    else:
        entry_layer_count = getattr(trade, "entry_layer_count", 0)

    return {
        "trade_id": getattr(trade, "trade_id", None),
        "opportunity_id": getattr(trade, "opportunity_id", conditions.get("opportunity_id")),
        "symbol": getattr(trade, "symbol", conditions.get("symbol")),
        "side": getattr(trade, "side", conditions.get("side")),
        "request_type": getattr(trade, "request_type", conditions.get("request_type")),
        "capital_lane": getattr(trade, "capital_lane", conditions.get("capital_lane")),
        "lineage_id": getattr(trade, "lineage_id", conditions.get("lineage_id")),
        "lineage_parent_trade_id": getattr(
            trade,
            "lineage_parent_trade_id",
            conditions.get("lineage_parent_trade_id"),
        ),
        "lineage_reentry_count": getattr(
            trade,
            "lineage_reentry_count",
            conditions.get("lineage_reentry_count"),
        ),
        "signal_family": getattr(trade, "signal_family", conditions.get("signal_family")),
        "edge_type": getattr(trade, "edge_type", conditions.get("edge_type")),
        "body_bucket": getattr(trade, "body_bucket", conditions.get("body_bucket")),
        "vwap_bucket": getattr(trade, "vwap_bucket", conditions.get("vwap_bucket")),
        "edge_bucket_key": getattr(trade, "edge_bucket_key", conditions.get("edge_bucket_key")),
        "bucket_expected_return": getattr(trade, "bucket_expected_return", conditions.get("bucket_expected_return")),
        "bucket_risk_mult": getattr(trade, "bucket_risk_mult", conditions.get("bucket_risk_mult")),
        "entry_time": getattr(trade, "entry_time", None),
        "exit_time": getattr(trade, "exit_time", None),
        "entry_price": getattr(trade, "entry_price", None),
        "exit_price": getattr(trade, "exit_price", None),
        "stop_price": getattr(trade, "stop", None),
        "active_stop_price": getattr(trade, "active_stop", getattr(trade, "stop", None)),
        "pnl": getattr(trade, "pnl", None),
        "pnl_R": getattr(trade, "pnl_R", None),
        "pnl_R_total": getattr(trade, "pnl_R_total", None),
        "pnl_R_initial": getattr(trade, "pnl_R_initial", None),
        "initial_risk_amount": getattr(trade, "initial_risk_amount", None),
        "total_risk_amount": getattr(trade, "total_risk_amount", None),
        "equity_at_entry": getattr(trade, "equity_at_entry", None),
        "entry_risk_multiplier": getattr(trade, "entry_risk_multiplier", None),
        "runtime_risk_multiplier": getattr(trade, "runtime_risk_multiplier", None),
        "intended_risk_per_trade": getattr(trade, "intended_risk_per_trade", None),
        "effective_risk_fraction": getattr(trade, "effective_risk_fraction", None),
        "equity_return_fraction": getattr(trade, "equity_return_fraction", None),
        "bias": getattr(trade, "bias", conditions.get("bias")),
        "regime_score": getattr(trade, "regime_score", conditions.get("regime_score")),
        "regime_class": getattr(trade, "regime_class", conditions.get("regime_class")),
        "entry_threshold": getattr(trade, "entry_threshold", conditions.get("entry_threshold")),
        "exit_reason": getattr(trade, "exit_reason", conditions.get("exit_reason")),
        "lifecycle_state": getattr(trade, "lifecycle_state", conditions.get("lifecycle_state")),
        "lifecycle_detail": getattr(trade, "lifecycle_detail", conditions.get("lifecycle_detail")),
        "lifecycle_updated_at": getattr(
            trade,
            "lifecycle_updated_at",
            conditions.get("lifecycle_updated_at"),
        ),
        "pressure_score": getattr(trade, "pressure_score", conditions.get("pressure_score")),
        "opportunity_score": getattr(trade, "opportunity_score", conditions.get("opportunity_score")),
        "score_bucket": getattr(trade, "score_bucket", conditions.get("score_bucket")),
        "momentum_rank": getattr(trade, "momentum_rank", conditions.get("momentum_rank")),
        "strategy_type": getattr(trade, "strategy_type", conditions.get("strategy_type")),
        "risk_group": getattr(trade, "risk_group", conditions.get("risk_group")),
        "selection_score": getattr(trade, "selection_score", conditions.get("selection_score")),
        "moonshot_score": getattr(trade, "moonshot_score", conditions.get("moonshot_score")),
        "range_expansion_factor": getattr(trade, "range_expansion_factor", conditions.get("range_expansion_factor")),
        "score_norm": getattr(trade, "score_norm", conditions.get("score_norm")),
        "momentum_strength": getattr(trade, "momentum_strength", conditions.get("momentum_strength")),
        "final_strength": getattr(trade, "final_strength", conditions.get("final_strength")),
        "bias_weight": getattr(trade, "bias_weight", conditions.get("bias_weight")),
        "regime_weight": getattr(trade, "regime_weight", conditions.get("regime_weight")),
        "event_bonus": getattr(trade, "event_bonus", conditions.get("event_bonus")),
        "trail_state": getattr(trade, "trail_state", conditions.get("trail_state")),
        "trail_anchor_column": getattr(trade, "trail_anchor_column", conditions.get("trail_anchor_column")),
        "trail_anchor_price": getattr(trade, "trail_anchor_price", conditions.get("trail_anchor_price")),
        "trail_open_r_multiple": getattr(trade, "trail_open_r_multiple", conditions.get("trail_open_r_multiple")),
        "trail_momentum_score": getattr(trade, "trail_momentum_score", conditions.get("trail_momentum_score")),
        "trail_decay_score": getattr(trade, "trail_decay_score", conditions.get("trail_decay_score")),
        "bars_held": getattr(trade, "bars_held", conditions.get("bars_held")),
        "max_hold_candles": getattr(trade, "max_hold_candles", conditions.get("max_hold_candles")),
        "trailing_activation_r": getattr(trade, "trailing_activation_r", conditions.get("trailing_activation_r")),
        "slow_grind_max_bars": getattr(trade, "slow_grind_max_bars", conditions.get("slow_grind_max_bars")),
        "slow_grind_open_r_max": getattr(trade, "slow_grind_open_r_max", conditions.get("slow_grind_open_r_max")),
        "entry_layer_count": entry_layer_count,
        "pyramid_level": getattr(trade, "pyramid_level", conditions.get("pyramid_level", 0)),
        "convexity_enabled": getattr(trade, "convexity_enabled", conditions.get("convexity_enabled")),
        "convexity_state": getattr(trade, "convexity_state", conditions.get("convexity_state")),
        "convexity_stage": getattr(trade, "convexity_stage", conditions.get("convexity_stage")),
        "convexity_base_risk_fraction": getattr(
            trade,
            "convexity_base_risk_fraction",
            conditions.get("convexity_base_risk_fraction"),
        ),
        "convexity_probe_fraction": getattr(
            trade,
            "convexity_probe_fraction",
            conditions.get("convexity_probe_fraction"),
        ),
        "convexity_target_risk_fraction": getattr(
            trade,
            "convexity_target_risk_fraction",
            conditions.get("convexity_target_risk_fraction"),
        ),
        "convexity_base_risk_amount": getattr(
            trade,
            "convexity_base_risk_amount",
            conditions.get("convexity_base_risk_amount"),
        ),
        "convexity_promote_target_multiple": getattr(
            trade,
            "convexity_promote_target_multiple",
            conditions.get("convexity_promote_target_multiple"),
        ),
        "convexity_add_target_multiple": getattr(
            trade,
            "convexity_add_target_multiple",
            conditions.get("convexity_add_target_multiple"),
        ),
        "convexity_max_target_multiple": getattr(
            trade,
            "convexity_max_target_multiple",
            conditions.get("convexity_max_target_multiple"),
        ),
        "convexity_add_count": getattr(
            trade,
            "convexity_add_count",
            conditions.get("convexity_add_count"),
        ),
        "convexity_last_add_bar": getattr(
            trade,
            "convexity_last_add_bar",
            conditions.get("convexity_last_add_bar"),
        ),
        "htf_signal_family": getattr(trade, "htf_signal_family", conditions.get("htf_signal_family")),
        "htf_score": getattr(trade, "htf_score", conditions.get("htf_score")),
        "htf_context_1d": getattr(trade, "htf_context_1d", conditions.get("htf_context_1d")),
        "htf_context_1w": getattr(trade, "htf_context_1w", conditions.get("htf_context_1w")),
        "htf_entry_reason": getattr(trade, "htf_entry_reason", conditions.get("htf_entry_reason")),
        "htf_stop_reason": getattr(trade, "htf_stop_reason", conditions.get("htf_stop_reason")),
        "htf_trailing_state": getattr(
            trade,
            "htf_trailing_state",
            conditions.get("htf_trailing_state"),
        ),
        "htf_decay_reason": getattr(trade, "htf_decay_reason", conditions.get("htf_decay_reason")),
        "htf_candidate_rank": getattr(trade, "htf_candidate_rank", conditions.get("htf_candidate_rank")),
        "score": conditions.get("score"),
        "body_strength": conditions.get("body_strength"),
        "close_position": conditions.get("close_position"),
        "upper_wick_ratio": conditions.get("upper_wick_ratio"),
        "lower_wick_ratio": conditions.get("lower_wick_ratio"),
        "compression": conditions.get("compression"),
        "breakout": conditions.get("breakout"),
        "breakdown": conditions.get("breakdown"),
        "session_vwap": conditions.get("session_vwap"),
        "vwap_distance_ratio": conditions.get("vwap_distance_ratio"),
        "ema_gap_ratio": conditions.get("ema_gap_ratio"),
        "atr": conditions.get("atr"),
        "macd_hist": conditions.get("macd_hist"),
    }


def _serialize_time(value):
    if value is None:
        return None

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value)


def _restore_time(value):
    if value is None or value == "":
        return None

    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return value


class Trade:
    """
    Represents a single trade lifecycle.

    A Trade stores the original setup context, all entry layers, the structural
    stop, the risk unit, exit state, and final PnL. It is the object passed
    between the simulator, account, and loggers so the reason and result of a
    trade remain connected.
    """

    def __init__(self, row, score, side="long", config=None):

        print("\nCreating new Trade object...")

        start = time.time()
        self.config = config or AppConfig.load()
        self.side = side
        high_period = self.config.require("features", "structure", "high_period")
        low_period = self.config.require("features", "structure", "low_period")
        self.stop_column = (
            f"ll{low_period}"
            if self.side == "long"
            else f"hh{high_period}"
        )

        # Entry info
        self.entry_time = row.name
        self.entry_price = row["close"]
        self.score = score
        self.trade_id = f"{self.side}_{_serialize_time(self.entry_time)}"
        self.opportunity_id = None
        self.symbol = None
        self.request_type = "fresh_entry"
        self.capital_lane = None
        self.lineage_id = None
        self.lineage_parent_trade_id = None
        self.lineage_reentry_count = 0

        # Structure
        self.stop = row[self.stop_column]
        self.active_stop = self.stop
        self.R = abs(self.entry_price - self.stop)

        # Position tracking
        self.entries = []           # [(price, size)]
        self.pyramid_level = 0

        # Exit info
        self.exit_time = None
        self.exit_price = None
        self.exit_reason = None

        # Results
        self.pnl = 0
        self.pnl_R = 0
        self.pnl_R_total = 0
        self.pnl_R_initial = 0
        self.initial_risk_amount = 0
        self.total_risk_amount = 0
        self.equity_at_entry = None
        self.signal_family = "trend"
        self.entry_risk_multiplier = 1.0
        self.runtime_risk_multiplier = 1.0
        self.entry_role = "core"
        self.entry_priority = 1
        self.intended_risk_per_trade = None
        self.effective_risk_fraction = None
        self.equity_return_fraction = None
        self.pressure_score = None
        self.opportunity_score = None
        self.score_bucket = None
        self.momentum_rank = None
        self.strategy_type = "core"
        self.risk_group = "core"
        self.selection_score = None
        self.moonshot_score = None
        self.range_expansion_factor = None
        self.feature_values = {}
        self.score_norm = None
        self.momentum_strength = None
        self.final_strength = None
        self.bias_weight = None
        self.regime_weight = None
        self.event_bonus = None
        self.bias = None
        self.regime_score = None
        self.regime_class = None
        self.entry_threshold = None
        self.lifecycle_state = "candidate"
        self.lifecycle_detail = "constructed"
        self.lifecycle_updated_at = self.entry_time
        self.edge_type = None
        self.body_bucket = None
        self.vwap_bucket = None
        self.edge_bucket_key = None
        self.bucket_expected_return = None
        self.bucket_risk_mult = None
        self.trail_state = "init"
        self.trail_anchor_column = None
        self.trail_anchor_price = None
        self.trail_open_r_multiple = 0.0
        self.trail_momentum_score = 0
        self.trail_decay_score = 0
        self.bars_held = 0
        self.max_hold_candles = None
        self.disable_pyramiding = False
        self.disable_trailing = False
        self.profit_lock_trigger_r = None
        self.profit_lock_stop_r = None
        self.trailing_activation_r = None
        self.slow_grind_max_bars = None
        self.slow_grind_open_r_max = None
        self.convexity_enabled = False
        self.convexity_state = "disabled"
        self.convexity_stage = 0
        self.convexity_base_risk_fraction = None
        self.convexity_probe_fraction = None
        self.convexity_target_risk_fraction = None
        self.convexity_base_risk_amount = None
        self.convexity_promote_target_multiple = None
        self.convexity_add_target_multiple = None
        self.convexity_max_target_multiple = None
        self.convexity_add_count = 0
        self.convexity_last_add_bar = 0
        self.htf_signal_family = None
        self.htf_score = None
        self.htf_context_1d = None
        self.htf_context_1w = None
        self.htf_entry_reason = None
        self.htf_stop_reason = None
        self.htf_trailing_state = None
        self.htf_decay_reason = None
        self.htf_candidate_rank = None

        # Store WHY trade happened (very important)
        self.conditions = {
            "side": side,
            "signal_family": self.signal_family,
            "opportunity_id": None,
            "symbol": None,
            "request_type": self.request_type,
            "capital_lane": self.capital_lane,
            "lineage_id": self.lineage_id,
            "lineage_parent_trade_id": self.lineage_parent_trade_id,
            "lineage_reentry_count": self.lineage_reentry_count,
            "score": score,
            "body_strength": row.get("body_strength", None),
            "close_position": row.get("close_position", None),
            "upper_wick_ratio": row.get("upper_wick_ratio", None),
            "lower_wick_ratio": row.get("lower_wick_ratio", None),
            "compression": row.get("compression", None),
            "breakout": row.get("breakout", None),
            "breakdown": row.get("breakdown", None),
            "session_vwap": row.get("session_vwap", None),
            "vwap_distance_ratio": row.get("vwap_distance_ratio", None),
            "ema_gap_ratio": row.get("ema_gap_ratio", None),
            "atr": row.get("atr", None),
            "macd_hist": row.get("macd_hist", None),
            "pressure_score": None,
            "opportunity_score": None,
            "score_bucket": None,
            "lifecycle_state": self.lifecycle_state,
            "lifecycle_detail": self.lifecycle_detail,
            "lifecycle_updated_at": self.lifecycle_updated_at,
            "momentum_rank": None,
            "strategy_type": self.strategy_type,
            "risk_group": self.risk_group,
            "selection_score": None,
            "moonshot_score": None,
            "range_expansion_factor": None,
            "edge_type": None,
            "body_bucket": None,
            "vwap_bucket": None,
            "edge_bucket_key": None,
            "bucket_expected_return": None,
            "bucket_risk_mult": None,
            "score_norm": None,
            "momentum_strength": None,
            "final_strength": None,
            "bias_weight": None,
            "regime_weight": None,
            "event_bonus": None,
            "bars_held": 0,
            "max_hold_candles": None,
            "trailing_activation_r": None,
            "slow_grind_max_bars": None,
            "slow_grind_open_r_max": None,
            "convexity_enabled": self.convexity_enabled,
            "convexity_state": self.convexity_state,
            "convexity_stage": self.convexity_stage,
            "convexity_base_risk_fraction": self.convexity_base_risk_fraction,
            "convexity_probe_fraction": self.convexity_probe_fraction,
            "convexity_target_risk_fraction": self.convexity_target_risk_fraction,
            "convexity_base_risk_amount": self.convexity_base_risk_amount,
            "convexity_promote_target_multiple": self.convexity_promote_target_multiple,
            "convexity_add_target_multiple": self.convexity_add_target_multiple,
            "convexity_max_target_multiple": self.convexity_max_target_multiple,
            "convexity_add_count": self.convexity_add_count,
            "convexity_last_add_bar": self.convexity_last_add_bar,
            "htf_signal_family": self.htf_signal_family,
            "htf_score": self.htf_score,
            "htf_context_1d": self.htf_context_1d,
            "htf_context_1w": self.htf_context_1w,
            "htf_entry_reason": self.htf_entry_reason,
            "htf_stop_reason": self.htf_stop_reason,
            "htf_trailing_state": self.htf_trailing_state,
            "htf_decay_reason": self.htf_decay_reason,
            "htf_candidate_rank": self.htf_candidate_rank,
        }

        print(f"Trade created at {self.entry_time}")
        print(f"  Side: {self.side}")
        print(f"  Entry price: {self.entry_price:.2f}")
        print(f"  Stop: {self.stop:.2f}")
        print(f"  R: {self.R:.2f}")

        print(f"Init elapsed: {time.time() - start:.4f}s")

    # ------------------------------------------
    # Add position (entry or pyramiding)
    # ------------------------------------------

    def add_entry(self, price, size):

        print("\nAdding position...")

        start = time.time()

        if not self.entries:
            self.initial_risk_amount = abs(price - self.stop) * size

        self.entries.append((price, size))

        print(f"Added: price={price:.2f}, size={size:.4f}")
        print(f"  Total entries: {len(self.entries)}")

        print(f"Elapsed: {time.time() - start:.4f}s")

    # ------------------------------------------
    # Close trade
    # ------------------------------------------

    def close(self, row, exit_price=None):

        print("\nClosing trade...")

        start = time.time()

        self.exit_time = row.name
        self.exit_price = row["close"] if exit_price is None else exit_price

        print(f"Exit time: {self.exit_time}")
        print(f"Exit price: {self.exit_price:.2f}")

        self.compute_pnl()

        print(f"Elapsed: {time.time() - start:.4f}s")

    # ------------------------------------------
    # Compute PnL
    # ------------------------------------------

    def total_risk_to_stop(self):
        """
        Compute current total stop-risk in quote currency terms.

        For each entry layer, the risk contribution is the distance from entry
        to the structural stop multiplied by the layer size. Summing across
        layers yields the total worst-case loss if price hits the stop.
        """

        return self.total_risk_to_stop_price(self.stop)

    def total_risk_to_stop_price(self, stop_price, floor_zero=False):
        if stop_price is None:
            return 0

        total = 0
        for entry_price, size in self.entries:
            if self.side == "short":
                risk_distance = float(stop_price) - float(entry_price)
            else:
                risk_distance = float(entry_price) - float(stop_price)
            if floor_zero:
                risk_distance = max(0.0, risk_distance)
            else:
                risk_distance = abs(risk_distance)
            total += risk_distance * float(size)

        return total

    def total_risk_to_active_stop(self):
        return self.total_risk_to_stop_price(self.active_stop, floor_zero=True)

    def compute_pnl(self):

        print("\nComputing PnL...")

        start = time.time()

        total = 0

        for entry_price, size in self.entries:
            if self.side == "short":
                move = entry_price - self.exit_price
            else:
                move = self.exit_price - entry_price
            pnl_part = move * size
            total += pnl_part

            print(f"  Entry: {entry_price:.2f} -> Exit: {self.exit_price:.2f} | PnL: {pnl_part:.2f}")

        self.pnl = total

        total_risk = self.total_risk_to_stop()
        self.total_risk_amount = total_risk

        if total_risk:
            self.pnl_R = total / total_risk
            self.pnl_R_total = self.pnl_R

        if self.initial_risk_amount:
            self.pnl_R_initial = total / self.initial_risk_amount

        if self.equity_at_entry:
            self.equity_return_fraction = total / self.equity_at_entry

        print(f"\nTotal PnL: {self.pnl:.2f}")
        print(f"PnL (R multiple, total risk): {self.pnl_R_total:.2f}")
        print(f"PnL (R multiple, initial risk): {self.pnl_R_initial:.2f}")
        if self.equity_return_fraction is not None:
            print(f"PnL (equity-normalized): {self.equity_return_fraction:.4f}")

        print(f"Elapsed: {time.time() - start:.4f}s")

    def annotate_entry_context(
        self,
        *,
        bias=None,
        regime_score=None,
        regime_class=None,
        entry_threshold=None,
        bias_snapshot=None,
        regime_snapshot=None,
    ):
        self.bias = bias
        self.regime_score = regime_score
        self.regime_class = regime_class
        self.entry_threshold = entry_threshold
        updates = {
            "bias": bias,
            "regime_score": regime_score,
            "regime_class": regime_class,
            "entry_threshold": entry_threshold,
        }
        if bias_snapshot:
            updates.update({
                "bias_price_vs_ema_ratio": bias_snapshot.get("price_vs_ema_ratio"),
                "bias_ema_slope": bias_snapshot.get("ema_slope"),
                "bias_directional_strength": bias_snapshot.get("directional_strength"),
            })
        if regime_snapshot:
            updates.update({
                "regime_max_score": regime_snapshot.get("max_score"),
                "regime_normalized_strength": regime_snapshot.get("normalized_strength"),
                "regime_macro_aligned": regime_snapshot.get("macro_aligned"),
                "regime_slope_aligned": regime_snapshot.get("slope_aligned"),
                "regime_trend_aligned": regime_snapshot.get("trend_aligned"),
            })
        self.conditions.update(updates)

    def annotate_exit(self, reason=None):
        self.exit_reason = reason
        self.conditions["exit_reason"] = reason

    def annotate_risk_context(
        self,
        *,
        equity_at_entry=None,
        entry_risk_multiplier=None,
        runtime_risk_multiplier=None,
        intended_risk_per_trade=None,
        effective_risk_fraction=None,
    ):
        self.equity_at_entry = equity_at_entry
        self.entry_risk_multiplier = entry_risk_multiplier
        self.runtime_risk_multiplier = runtime_risk_multiplier
        self.intended_risk_per_trade = intended_risk_per_trade
        self.effective_risk_fraction = effective_risk_fraction
        self.conditions.update({
            "equity_at_entry": equity_at_entry,
            "entry_risk_multiplier": entry_risk_multiplier,
            "runtime_risk_multiplier": runtime_risk_multiplier,
            "intended_risk_per_trade": intended_risk_per_trade,
            "effective_risk_fraction": effective_risk_fraction,
        })

    def annotate_signal_family(self, signal_family, pressure_score=None):
        self.signal_family = signal_family
        self.pressure_score = pressure_score
        self.conditions.update({
            "signal_family": signal_family,
            "pressure_score": pressure_score,
        })

    def annotate_opportunity(self, opportunity_id=None):
        self.opportunity_id = opportunity_id
        self.conditions["opportunity_id"] = opportunity_id

    def annotate_capital_request(
        self,
        *,
        request_type=None,
        capital_lane=None,
        lineage_id=None,
        lineage_parent_trade_id=None,
        lineage_reentry_count=None,
    ):
        if request_type is not None:
            self.request_type = str(request_type)
        if capital_lane is not None:
            self.capital_lane = str(capital_lane)
        if lineage_id is not None:
            self.lineage_id = str(lineage_id)
        if lineage_parent_trade_id is not None:
            self.lineage_parent_trade_id = str(lineage_parent_trade_id)
        if lineage_reentry_count is not None:
            self.lineage_reentry_count = int(lineage_reentry_count or 0)
        self.conditions.update(
            {
                "request_type": self.request_type,
                "capital_lane": self.capital_lane,
                "lineage_id": self.lineage_id,
                "lineage_parent_trade_id": self.lineage_parent_trade_id,
                "lineage_reentry_count": self.lineage_reentry_count,
            }
        )

    def transition_lifecycle(self, state, *, detail=None, timestamp=None):
        self.lifecycle_state = str(state or self.lifecycle_state or "candidate")
        if detail is not None:
            self.lifecycle_detail = str(detail)
        normalized_time = _restore_time(_serialize_time(timestamp)) if timestamp is not None else None
        self.lifecycle_updated_at = normalized_time or self.lifecycle_updated_at or self.entry_time
        self.conditions.update(
            {
                "lifecycle_state": self.lifecycle_state,
                "lifecycle_detail": self.lifecycle_detail,
                "lifecycle_updated_at": self.lifecycle_updated_at,
            }
        )
        return self.lifecycle_state

    def annotate_live_scoring(
        self,
        *,
        symbol=None,
        opportunity_score=None,
        score_bucket=None,
        momentum_rank=None,
        feature_values=None,
        strategy_type=None,
        risk_group=None,
        selection_score=None,
        moonshot_score=None,
        range_expansion_factor=None,
    ):
        self.symbol = symbol
        self.opportunity_score = opportunity_score
        self.score_bucket = score_bucket
        self.momentum_rank = momentum_rank
        self.strategy_type = strategy_type or self.strategy_type
        self.risk_group = risk_group or self.risk_group
        self.selection_score = selection_score
        self.moonshot_score = moonshot_score
        self.range_expansion_factor = range_expansion_factor
        self.feature_values = dict(feature_values or {})
        self.conditions.update(
            {
                "symbol": symbol,
                "opportunity_score": opportunity_score,
                "score_bucket": score_bucket,
                "momentum_rank": momentum_rank,
                "strategy_type": self.strategy_type,
                "risk_group": self.risk_group,
                "selection_score": selection_score,
                "moonshot_score": moonshot_score,
                "range_expansion_factor": range_expansion_factor,
            }
        )

    def annotate_weighted_context(
        self,
        *,
        score_norm=None,
        momentum_strength=None,
        final_strength=None,
        bias_weight=None,
        regime_weight=None,
        event_bonus=None,
    ):
        self.score_norm = score_norm
        self.momentum_strength = momentum_strength
        self.final_strength = final_strength
        self.bias_weight = bias_weight
        self.regime_weight = regime_weight
        self.event_bonus = event_bonus
        self.conditions.update({
            "score_norm": score_norm,
            "momentum_strength": momentum_strength,
            "final_strength": final_strength,
            "bias_weight": bias_weight,
            "regime_weight": regime_weight,
            "event_bonus": event_bonus,
        })

    def annotate_edge_bucket(
        self,
        *,
        edge_type=None,
        body_bucket=None,
        vwap_bucket=None,
        bucket_key=None,
        bucket_expected_return=None,
        bucket_risk_mult=None,
    ):
        self.edge_type = edge_type
        self.body_bucket = body_bucket
        self.vwap_bucket = vwap_bucket
        self.edge_bucket_key = bucket_key
        self.bucket_expected_return = bucket_expected_return
        self.bucket_risk_mult = bucket_risk_mult
        self.conditions.update({
            "edge_type": edge_type,
            "body_bucket": body_bucket,
            "vwap_bucket": vwap_bucket,
            "edge_bucket_key": bucket_key,
            "bucket_expected_return": bucket_expected_return,
            "bucket_risk_mult": bucket_risk_mult,
        })

    def annotate_edge_execution_profile(
        self,
        *,
        max_hold_candles=None,
        disable_pyramiding=False,
        disable_trailing=False,
        profit_lock_trigger_r=None,
        profit_lock_stop_r=None,
        trailing_activation_r=None,
        slow_grind_max_bars=None,
        slow_grind_open_r_max=None,
    ):
        self.max_hold_candles = (
            None if max_hold_candles in (None, "") else int(max_hold_candles)
        )
        self.disable_pyramiding = bool(disable_pyramiding)
        self.disable_trailing = bool(disable_trailing)
        self.profit_lock_trigger_r = (
            None if profit_lock_trigger_r in (None, "") else float(profit_lock_trigger_r)
        )
        self.profit_lock_stop_r = (
            None if profit_lock_stop_r in (None, "") else float(profit_lock_stop_r)
        )
        self.trailing_activation_r = (
            None if trailing_activation_r in (None, "") else float(trailing_activation_r)
        )
        self.slow_grind_max_bars = (
            None if slow_grind_max_bars in (None, "") else int(slow_grind_max_bars)
        )
        self.slow_grind_open_r_max = (
            None if slow_grind_open_r_max in (None, "") else float(slow_grind_open_r_max)
        )
        self.conditions.update(
            {
                "max_hold_candles": self.max_hold_candles,
                "disable_pyramiding": self.disable_pyramiding,
                "disable_trailing": self.disable_trailing,
                "profit_lock_trigger_r": self.profit_lock_trigger_r,
                "profit_lock_stop_r": self.profit_lock_stop_r,
                "trailing_activation_r": self.trailing_activation_r,
                "slow_grind_max_bars": self.slow_grind_max_bars,
                "slow_grind_open_r_max": self.slow_grind_open_r_max,
            }
        )

    def annotate_htf_context(
        self,
        *,
        signal_family=None,
        htf_score=None,
        context_1d=None,
        context_1w=None,
        entry_reason=None,
        stop_reason=None,
        trailing_state=None,
        decay_reason=None,
        candidate_rank=None,
    ):
        self.htf_signal_family = signal_family
        self.htf_score = htf_score
        self.htf_context_1d = context_1d
        self.htf_context_1w = context_1w
        self.htf_entry_reason = entry_reason
        self.htf_stop_reason = stop_reason
        self.htf_trailing_state = trailing_state
        self.htf_decay_reason = decay_reason
        self.htf_candidate_rank = candidate_rank
        self.conditions.update(
            {
                "htf_signal_family": signal_family,
                "htf_score": htf_score,
                "htf_context_1d": context_1d,
                "htf_context_1w": context_1w,
                "htf_entry_reason": entry_reason,
                "htf_stop_reason": stop_reason,
                "htf_trailing_state": trailing_state,
                "htf_decay_reason": decay_reason,
                "htf_candidate_rank": candidate_rank,
            }
        )

    def annotate_convexity_profile(
        self,
        *,
        enabled=False,
        state="disabled",
        stage=0,
        base_risk_fraction=None,
        probe_fraction=None,
        target_risk_fraction=None,
        base_risk_amount=None,
        promote_target_multiple=None,
        add_target_multiple=None,
        max_target_multiple=None,
        add_count=None,
        last_add_bar=None,
    ):
        self.convexity_enabled = bool(enabled)
        self.convexity_state = str(state or "disabled")
        self.convexity_stage = int(stage or 0)
        self.convexity_base_risk_fraction = (
            None if base_risk_fraction in (None, "") else float(base_risk_fraction)
        )
        self.convexity_probe_fraction = (
            None if probe_fraction in (None, "") else float(probe_fraction)
        )
        self.convexity_target_risk_fraction = (
            None if target_risk_fraction in (None, "") else float(target_risk_fraction)
        )
        self.convexity_base_risk_amount = (
            None if base_risk_amount in (None, "") else float(base_risk_amount)
        )
        self.convexity_promote_target_multiple = (
            None
            if promote_target_multiple in (None, "")
            else float(promote_target_multiple)
        )
        self.convexity_add_target_multiple = (
            None if add_target_multiple in (None, "") else float(add_target_multiple)
        )
        self.convexity_max_target_multiple = (
            None if max_target_multiple in (None, "") else float(max_target_multiple)
        )
        self.convexity_add_count = int(add_count or 0)
        self.convexity_last_add_bar = int(last_add_bar or 0)
        self.conditions.update(
            {
                "convexity_enabled": self.convexity_enabled,
                "convexity_state": self.convexity_state,
                "convexity_stage": self.convexity_stage,
                "convexity_base_risk_fraction": self.convexity_base_risk_fraction,
                "convexity_probe_fraction": self.convexity_probe_fraction,
                "convexity_target_risk_fraction": self.convexity_target_risk_fraction,
                "convexity_base_risk_amount": self.convexity_base_risk_amount,
                "convexity_promote_target_multiple": self.convexity_promote_target_multiple,
                "convexity_add_target_multiple": self.convexity_add_target_multiple,
                "convexity_max_target_multiple": self.convexity_max_target_multiple,
                "convexity_add_count": self.convexity_add_count,
                "convexity_last_add_bar": self.convexity_last_add_bar,
            }
        )

    def advance_bar(self):
        self.bars_held = int(self.bars_held or 0) + 1
        self.conditions["bars_held"] = self.bars_held
        return self.bars_held

    def update_trailing_state(
        self,
        *,
        trail_state,
        anchor_column=None,
        anchor_price=None,
        open_r_multiple=None,
        momentum_score=None,
        decay_score=None,
        proposed_stop=None,
    ):
        self.trail_state = trail_state
        self.trail_anchor_column = anchor_column
        self.trail_anchor_price = anchor_price
        self.trail_open_r_multiple = open_r_multiple
        self.trail_momentum_score = momentum_score
        self.trail_decay_score = decay_score
        self.conditions.update(
            {
                "trail_state": trail_state,
                "trail_anchor_column": anchor_column,
                "trail_anchor_price": anchor_price,
                "trail_open_r_multiple": open_r_multiple,
                "trail_momentum_score": momentum_score,
                "trail_decay_score": decay_score,
            }
        )

        if proposed_stop is None:
            return self.active_stop

        if self.side == "short":
            self.active_stop = min(float(self.active_stop), float(proposed_stop))
        else:
            self.active_stop = max(float(self.active_stop), float(proposed_stop))

        return self.active_stop

    def snapshot(self):
        return {
            "stop_column": self.stop_column,
            "side": self.side,
            "signal_family": self.signal_family,
            "symbol": self.symbol,
            "entry_time": _serialize_time(self.entry_time),
            "entry_price": self.entry_price,
            "score": self.score,
            "trade_id": self.trade_id,
            "opportunity_id": self.opportunity_id,
            "stop": self.stop,
            "active_stop": self.active_stop,
            "R": self.R,
            "request_type": self.request_type,
            "capital_lane": self.capital_lane,
            "lineage_id": self.lineage_id,
            "lineage_parent_trade_id": self.lineage_parent_trade_id,
            "lineage_reentry_count": self.lineage_reentry_count,
            "entries": [
                {
                    "price": entry_price,
                    "size": size,
                }
                for entry_price, size in self.entries
            ],
            "pyramid_level": self.pyramid_level,
            "exit_time": _serialize_time(self.exit_time),
            "exit_price": self.exit_price,
            "exit_reason": self.exit_reason,
            "pnl": self.pnl,
            "pnl_R": self.pnl_R,
            "pnl_R_total": self.pnl_R_total,
            "pnl_R_initial": self.pnl_R_initial,
            "initial_risk_amount": self.initial_risk_amount,
            "total_risk_amount": self.total_risk_amount,
            "equity_at_entry": self.equity_at_entry,
            "entry_risk_multiplier": self.entry_risk_multiplier,
            "entry_role": self.entry_role,
            "entry_priority": self.entry_priority,
            "intended_risk_per_trade": self.intended_risk_per_trade,
            "effective_risk_fraction": self.effective_risk_fraction,
            "equity_return_fraction": self.equity_return_fraction,
            "pressure_score": self.pressure_score,
            "opportunity_score": self.opportunity_score,
            "score_bucket": self.score_bucket,
            "momentum_rank": self.momentum_rank,
            "strategy_type": self.strategy_type,
            "risk_group": self.risk_group,
            "selection_score": self.selection_score,
            "moonshot_score": self.moonshot_score,
            "range_expansion_factor": self.range_expansion_factor,
            "feature_values": dict(self.feature_values),
            "score_norm": self.score_norm,
            "momentum_strength": self.momentum_strength,
            "final_strength": self.final_strength,
            "bias_weight": self.bias_weight,
            "regime_weight": self.regime_weight,
            "event_bonus": self.event_bonus,
            "bias": self.bias,
            "regime_score": self.regime_score,
            "regime_class": self.regime_class,
            "entry_threshold": self.entry_threshold,
            "lifecycle_state": self.lifecycle_state,
            "lifecycle_detail": self.lifecycle_detail,
            "lifecycle_updated_at": _serialize_time(self.lifecycle_updated_at),
            "trail_state": self.trail_state,
            "trail_anchor_column": self.trail_anchor_column,
            "trail_anchor_price": self.trail_anchor_price,
            "trail_open_r_multiple": self.trail_open_r_multiple,
            "trail_momentum_score": self.trail_momentum_score,
            "trail_decay_score": self.trail_decay_score,
            "bars_held": self.bars_held,
            "max_hold_candles": self.max_hold_candles,
            "disable_pyramiding": self.disable_pyramiding,
            "disable_trailing": self.disable_trailing,
            "profit_lock_trigger_r": self.profit_lock_trigger_r,
            "profit_lock_stop_r": self.profit_lock_stop_r,
            "trailing_activation_r": self.trailing_activation_r,
            "slow_grind_max_bars": self.slow_grind_max_bars,
            "slow_grind_open_r_max": self.slow_grind_open_r_max,
            "convexity_enabled": self.convexity_enabled,
            "convexity_state": self.convexity_state,
            "convexity_stage": self.convexity_stage,
            "convexity_base_risk_fraction": self.convexity_base_risk_fraction,
            "convexity_probe_fraction": self.convexity_probe_fraction,
            "convexity_target_risk_fraction": self.convexity_target_risk_fraction,
            "convexity_base_risk_amount": self.convexity_base_risk_amount,
            "convexity_promote_target_multiple": self.convexity_promote_target_multiple,
            "convexity_add_target_multiple": self.convexity_add_target_multiple,
            "convexity_max_target_multiple": self.convexity_max_target_multiple,
            "convexity_add_count": self.convexity_add_count,
            "convexity_last_add_bar": self.convexity_last_add_bar,
            "htf_signal_family": self.htf_signal_family,
            "htf_score": self.htf_score,
            "htf_context_1d": self.htf_context_1d,
            "htf_context_1w": self.htf_context_1w,
            "htf_entry_reason": self.htf_entry_reason,
            "htf_stop_reason": self.htf_stop_reason,
            "htf_trailing_state": self.htf_trailing_state,
            "htf_decay_reason": self.htf_decay_reason,
            "htf_candidate_rank": self.htf_candidate_rank,
            "conditions": dict(self.conditions),
        }

    @classmethod
    def from_snapshot(cls, snapshot, config=None):
        trade = cls.__new__(cls)
        trade.config = config or AppConfig.load()
        high_period = trade.config.require("features", "structure", "high_period")
        low_period = trade.config.require("features", "structure", "low_period")
        trade.side = snapshot.get("side", "long")
        trade.signal_family = snapshot.get("signal_family", "trend")
        trade.symbol = snapshot.get("symbol")
        default_stop_column = (
            f"ll{low_period}"
            if trade.side == "long"
            else f"hh{high_period}"
        )
        trade.stop_column = snapshot.get("stop_column") or default_stop_column
        trade.entry_time = _restore_time(snapshot.get("entry_time"))
        trade.entry_price = snapshot.get("entry_price")
        trade.score = snapshot.get("score")
        trade.trade_id = snapshot.get("trade_id") or f"{trade.side}_{_serialize_time(trade.entry_time)}"
        trade.opportunity_id = snapshot.get("opportunity_id")
        trade.stop = snapshot.get("stop")
        trade.active_stop = snapshot.get("active_stop", trade.stop)
        trade.R = snapshot.get("R")
        trade.request_type = snapshot.get("request_type", "fresh_entry")
        trade.capital_lane = snapshot.get("capital_lane")
        trade.lineage_id = snapshot.get("lineage_id")
        trade.lineage_parent_trade_id = snapshot.get("lineage_parent_trade_id")
        trade.lineage_reentry_count = snapshot.get("lineage_reentry_count", 0)
        trade.entries = [
            (entry.get("price"), entry.get("size"))
            for entry in snapshot.get("entries", [])
        ]
        trade.pyramid_level = snapshot.get("pyramid_level", 0)
        trade.exit_time = _restore_time(snapshot.get("exit_time"))
        trade.exit_price = snapshot.get("exit_price")
        trade.exit_reason = snapshot.get("exit_reason")
        trade.pnl = snapshot.get("pnl", 0)
        trade.pnl_R = snapshot.get("pnl_R", 0)
        trade.pnl_R_total = snapshot.get("pnl_R_total", 0)
        trade.pnl_R_initial = snapshot.get("pnl_R_initial", 0)
        trade.initial_risk_amount = snapshot.get("initial_risk_amount", 0)
        trade.total_risk_amount = snapshot.get("total_risk_amount", 0)
        trade.equity_at_entry = snapshot.get("equity_at_entry")
        trade.entry_risk_multiplier = snapshot.get("entry_risk_multiplier", 1.0)
        trade.entry_role = snapshot.get("entry_role", "core")
        trade.entry_priority = snapshot.get("entry_priority", 1)
        trade.intended_risk_per_trade = snapshot.get("intended_risk_per_trade")
        trade.effective_risk_fraction = snapshot.get("effective_risk_fraction")
        trade.equity_return_fraction = snapshot.get("equity_return_fraction")
        trade.pressure_score = snapshot.get("pressure_score")
        trade.opportunity_score = snapshot.get("opportunity_score")
        trade.score_bucket = snapshot.get("score_bucket")
        trade.momentum_rank = snapshot.get("momentum_rank")
        trade.strategy_type = snapshot.get("strategy_type", "core")
        trade.risk_group = snapshot.get("risk_group", "core")
        trade.selection_score = snapshot.get("selection_score")
        trade.moonshot_score = snapshot.get("moonshot_score")
        trade.range_expansion_factor = snapshot.get("range_expansion_factor")
        trade.feature_values = dict(snapshot.get("feature_values", {}) or {})
        trade.score_norm = snapshot.get("score_norm")
        trade.momentum_strength = snapshot.get("momentum_strength")
        trade.final_strength = snapshot.get("final_strength")
        trade.bias_weight = snapshot.get("bias_weight")
        trade.regime_weight = snapshot.get("regime_weight")
        trade.event_bonus = snapshot.get("event_bonus")
        trade.bias = snapshot.get("bias")
        trade.regime_score = snapshot.get("regime_score")
        trade.regime_class = snapshot.get("regime_class")
        trade.entry_threshold = snapshot.get("entry_threshold")
        trade.lifecycle_state = snapshot.get("lifecycle_state", "candidate")
        trade.lifecycle_detail = snapshot.get("lifecycle_detail", "restored")
        trade.lifecycle_updated_at = _restore_time(snapshot.get("lifecycle_updated_at"))
        trade.trail_state = snapshot.get("trail_state", "init")
        trade.trail_anchor_column = snapshot.get("trail_anchor_column")
        trade.trail_anchor_price = snapshot.get("trail_anchor_price")
        trade.trail_open_r_multiple = snapshot.get("trail_open_r_multiple", 0.0)
        trade.trail_momentum_score = snapshot.get("trail_momentum_score", 0)
        trade.trail_decay_score = snapshot.get("trail_decay_score", 0)
        trade.bars_held = snapshot.get("bars_held", 0)
        trade.max_hold_candles = snapshot.get("max_hold_candles")
        trade.disable_pyramiding = snapshot.get("disable_pyramiding", False)
        trade.disable_trailing = snapshot.get("disable_trailing", False)
        trade.profit_lock_trigger_r = snapshot.get("profit_lock_trigger_r")
        trade.profit_lock_stop_r = snapshot.get("profit_lock_stop_r")
        trade.trailing_activation_r = snapshot.get("trailing_activation_r")
        trade.slow_grind_max_bars = snapshot.get("slow_grind_max_bars")
        trade.slow_grind_open_r_max = snapshot.get("slow_grind_open_r_max")
        trade.convexity_enabled = snapshot.get("convexity_enabled", False)
        trade.convexity_state = snapshot.get("convexity_state", "disabled")
        trade.convexity_stage = snapshot.get("convexity_stage", 0)
        trade.convexity_base_risk_fraction = snapshot.get("convexity_base_risk_fraction")
        trade.convexity_probe_fraction = snapshot.get("convexity_probe_fraction")
        trade.convexity_target_risk_fraction = snapshot.get("convexity_target_risk_fraction")
        trade.convexity_base_risk_amount = snapshot.get("convexity_base_risk_amount")
        trade.convexity_promote_target_multiple = snapshot.get("convexity_promote_target_multiple")
        trade.convexity_add_target_multiple = snapshot.get("convexity_add_target_multiple")
        trade.convexity_max_target_multiple = snapshot.get("convexity_max_target_multiple")
        trade.convexity_add_count = snapshot.get("convexity_add_count", 0)
        trade.convexity_last_add_bar = snapshot.get("convexity_last_add_bar", 0)
        trade.htf_signal_family = snapshot.get("htf_signal_family")
        trade.htf_score = snapshot.get("htf_score")
        trade.htf_context_1d = snapshot.get("htf_context_1d")
        trade.htf_context_1w = snapshot.get("htf_context_1w")
        trade.htf_entry_reason = snapshot.get("htf_entry_reason")
        trade.htf_stop_reason = snapshot.get("htf_stop_reason")
        trade.htf_trailing_state = snapshot.get("htf_trailing_state")
        trade.htf_decay_reason = snapshot.get("htf_decay_reason")
        trade.htf_candidate_rank = snapshot.get("htf_candidate_rank")
        trade.conditions = dict(snapshot.get("conditions", {}))
        return trade
