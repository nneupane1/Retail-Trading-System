"""Represents the full lifecycle of one trade, including entries, exits, and PnL."""

import time
from datetime import datetime

from common.debug import debug_print as print
from config import AppConfig


TRADE_LOG_FIELDS = [
    "entry_time",
    "exit_time",
    "entry_price",
    "exit_price",
    "pnl",
    "pnl_R",
    "pnl_R_total",
    "pnl_R_initial",
    "initial_risk_amount",
    "total_risk_amount",
    "bias",
    "regime_score",
    "regime_class",
    "entry_threshold",
    "exit_reason",
    "entry_layer_count",
    "pyramid_level",
    "score",
    "body_strength",
    "close_position",
    "upper_wick_ratio",
    "compression",
    "breakout",
]


def trade_to_log_record(trade):
    conditions = getattr(trade, "conditions", {}) or {}
    entries = getattr(trade, "entries", None)
    if entries is not None:
        entry_layer_count = len(entries)
    else:
        entry_layer_count = getattr(trade, "entry_layer_count", 0)

    return {
        "entry_time": getattr(trade, "entry_time", None),
        "exit_time": getattr(trade, "exit_time", None),
        "entry_price": getattr(trade, "entry_price", None),
        "exit_price": getattr(trade, "exit_price", None),
        "pnl": getattr(trade, "pnl", None),
        "pnl_R": getattr(trade, "pnl_R", None),
        "pnl_R_total": getattr(trade, "pnl_R_total", None),
        "pnl_R_initial": getattr(trade, "pnl_R_initial", None),
        "initial_risk_amount": getattr(trade, "initial_risk_amount", None),
        "total_risk_amount": getattr(trade, "total_risk_amount", None),
        "bias": getattr(trade, "bias", conditions.get("bias")),
        "regime_score": getattr(trade, "regime_score", conditions.get("regime_score")),
        "regime_class": getattr(trade, "regime_class", conditions.get("regime_class")),
        "entry_threshold": getattr(trade, "entry_threshold", conditions.get("entry_threshold")),
        "exit_reason": getattr(trade, "exit_reason", conditions.get("exit_reason")),
        "entry_layer_count": entry_layer_count,
        "pyramid_level": getattr(trade, "pyramid_level", conditions.get("pyramid_level", 0)),
        "score": conditions.get("score"),
        "body_strength": conditions.get("body_strength"),
        "close_position": conditions.get("close_position"),
        "upper_wick_ratio": conditions.get("upper_wick_ratio"),
        "compression": conditions.get("compression"),
        "breakout": conditions.get("breakout"),
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

    def __init__(self, row, score, config=None):

        print("\nCreating new Trade object...")

        start = time.time()
        self.config = config or AppConfig.load()
        low_period = self.config.require("features", "structure", "low_period")
        self.stop_column = f"ll{low_period}"

        # Entry info
        self.entry_time = row.name
        self.entry_price = row["close"]
        self.score = score

        # Structure
        self.stop = row[self.stop_column]     # stop = recent low
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
        self.bias = None
        self.regime_score = None
        self.regime_class = None
        self.entry_threshold = None

        # Store WHY trade happened (very important)
        self.conditions = {
            "score": score,
            "body_strength": row.get("body_strength", None),
            "close_position": row.get("close_position", None),
            "upper_wick_ratio": row.get("upper_wick_ratio", None),
            "compression": row.get("compression", None),
            "breakout": row.get("breakout", None),
        }

        print(f"Trade created at {self.entry_time}")
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

        if self.stop is None:
            return 0

        total = 0
        for entry_price, size in self.entries:
            total += abs(entry_price - self.stop) * size

        return total

    def compute_pnl(self):

        print("\nComputing PnL...")

        start = time.time()

        total = 0

        for entry_price, size in self.entries:
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

        print(f"\nTotal PnL: {self.pnl:.2f}")
        print(f"PnL (R multiple, total risk): {self.pnl_R_total:.2f}")
        print(f"PnL (R multiple, initial risk): {self.pnl_R_initial:.2f}")

        print(f"Elapsed: {time.time() - start:.4f}s")

    def annotate_entry_context(
        self,
        *,
        bias=None,
        regime_score=None,
        regime_class=None,
        entry_threshold=None
    ):
        self.bias = bias
        self.regime_score = regime_score
        self.regime_class = regime_class
        self.entry_threshold = entry_threshold
        self.conditions.update({
            "bias": bias,
            "regime_score": regime_score,
            "regime_class": regime_class,
            "entry_threshold": entry_threshold,
        })

    def annotate_exit(self, reason=None):
        self.exit_reason = reason
        self.conditions["exit_reason"] = reason

    def snapshot(self):
        return {
            "stop_column": self.stop_column,
            "entry_time": _serialize_time(self.entry_time),
            "entry_price": self.entry_price,
            "score": self.score,
            "stop": self.stop,
            "R": self.R,
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
            "bias": self.bias,
            "regime_score": self.regime_score,
            "regime_class": self.regime_class,
            "entry_threshold": self.entry_threshold,
            "conditions": dict(self.conditions),
        }

    @classmethod
    def from_snapshot(cls, snapshot, config=None):
        trade = cls.__new__(cls)
        trade.config = config or AppConfig.load()
        low_period = trade.config.require("features", "structure", "low_period")
        trade.stop_column = snapshot.get("stop_column") or f"ll{low_period}"
        trade.entry_time = _restore_time(snapshot.get("entry_time"))
        trade.entry_price = snapshot.get("entry_price")
        trade.score = snapshot.get("score")
        trade.stop = snapshot.get("stop")
        trade.R = snapshot.get("R")
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
        trade.bias = snapshot.get("bias")
        trade.regime_score = snapshot.get("regime_score")
        trade.regime_class = snapshot.get("regime_class")
        trade.entry_threshold = snapshot.get("entry_threshold")
        trade.conditions = dict(snapshot.get("conditions", {}))
        return trade
