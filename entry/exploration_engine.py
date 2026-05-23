"""Generates small exploratory trades when pressure build-up ignites into directional expansion."""

import time

from common.debug import debug_print as print
from config import AppConfig
from simulation.trade import Trade


class ExplorationEngine:
    """
    Builds low-risk exploratory entries from pressure/ignition features.

    The goal is not high-confidence trend confirmation. The goal is to deploy
    small capital into early instability transitions, then let the existing
    trend-following and trailing machinery decide whether the move matures.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        getter = getattr(self.config, "get", None)
        exploration = getter("strategy", "exploration", default={}) if callable(getter) else {}
        exploration = exploration or {}

        self.enabled = bool(exploration.get("enabled", False))
        self.enabled_sides = {
            str(side).lower()
            for side in exploration.get("enabled_sides", ["long", "short"])
        }
        self.allow_neutral_bias = bool(exploration.get("allow_neutral_bias", True))
        self.block_opposite_bias = bool(exploration.get("block_opposite_bias", True))
        self.require_atr_rising = bool(exploration.get("require_atr_rising", True))
        self.require_vwap_alignment = bool(exploration.get("require_vwap_alignment", False))
        self.require_macd_alignment = bool(exploration.get("require_macd_alignment", False))
        self.minimum_regime_score = exploration.get("minimum_regime_score", None)
        self.allowed_regime_classes = {
            str(value).lower()
            for value in (exploration.get("allowed_regime_classes", []) or [])
        }
        self.entry_priority = int(exploration.get("entry_priority", 0))
        self.entry_role = str(exploration.get("entry_role", "support")).lower()
        self.signal_family = "exploratory"

        threshold_by_side = exploration.get("pressure_score_threshold_by_side", {}) or {}
        self.pressure_score_threshold = int(exploration.get("pressure_score_threshold", 3))
        self.pressure_score_threshold_by_side = {
            str(side).lower(): int(value)
            for side, value in threshold_by_side.items()
        }

        multiplier_by_side = exploration.get("entry_risk_multiplier_by_side", {}) or {}
        self.entry_risk_multiplier = float(exploration.get("entry_risk_multiplier", 0.25))
        self.entry_risk_multiplier_by_side = {
            str(side).lower(): float(value)
            for side, value in multiplier_by_side.items()
        }

    def _pressure_threshold_for_side(self, side):
        return self.pressure_score_threshold_by_side.get(side, self.pressure_score_threshold)

    def _risk_multiplier_for_side(self, side):
        return self.entry_risk_multiplier_by_side.get(side, self.entry_risk_multiplier)

    @staticmethod
    def _required_bias(side):
        return "bullish" if side == "long" else "bearish"

    @staticmethod
    def _opposite_bias(side):
        return "bearish" if side == "long" else "bullish"

    def _passes_bias_gate(self, bias, side):
        required_bias = self._required_bias(side)
        opposite_bias = self._opposite_bias(side)

        if self.block_opposite_bias and bias == opposite_bias:
            return False
        if bias == required_bias:
            return True
        if self.allow_neutral_bias and str(bias).lower() == "neutral":
            return True
        return not self.block_opposite_bias

    def _passes_regime_gate(self, regime_score, regime_class):
        if self.minimum_regime_score is not None and regime_score is not None:
            if float(regime_score) < float(self.minimum_regime_score):
                return False
        if self.allowed_regime_classes:
            if str(regime_class or "").lower() not in self.allowed_regime_classes:
                return False
        return True

    def build_candidate(
        self,
        row,
        *,
        bias,
        side,
        regime_score=None,
        regime_class=None,
    ):
        start = time.time()
        side = str(side).lower()

        if not self.enabled or side not in self.enabled_sides:
            return None

        if not self._passes_bias_gate(bias, side):
            print(f"No exploratory {side} entry: bias gate blocked candidate")
            return None

        if not self._passes_regime_gate(regime_score, regime_class):
            print(f"No exploratory {side} entry: regime gate blocked candidate")
            return None

        pressure_column = f"pressure_score_{side}"
        ignition_column = f"pressure_ignition_{side}"
        pressure_score = int(row.get(pressure_column, 0) or 0)
        ignition = bool(row.get(ignition_column, False))
        threshold = self._pressure_threshold_for_side(side)

        if pressure_score < threshold:
            print(
                f"No exploratory {side} entry: pressure score too low "
                f"({pressure_score} < {threshold})"
            )
            return None

        if not ignition:
            print(f"No exploratory {side} entry: no ignition event")
            return None

        if self.require_atr_rising and not bool(row.get("atr_rising", False)):
            print(f"No exploratory {side} entry: ATR not expanding")
            return None

        if self.require_vwap_alignment:
            price = float(row.get("close", 0.0))
            vwap = float(row.get("session_vwap", price))
            aligned = price >= vwap if side == "long" else price <= vwap
            if not aligned:
                print(f"No exploratory {side} entry: VWAP alignment missing")
                return None

        if self.require_macd_alignment:
            macd_hist = float(row.get("macd_hist", 0.0))
            aligned = macd_hist >= 0.0 if side == "long" else macd_hist <= 0.0
            if not aligned:
                print(f"No exploratory {side} entry: MACD alignment missing")
                return None

        trade = Trade(row, pressure_score, side=side, config=self.config)
        trade.entry_risk_multiplier = self._risk_multiplier_for_side(side)
        trade.entry_role = self.entry_role
        trade.entry_priority = self.entry_priority
        if hasattr(trade, "annotate_signal_family"):
            trade.annotate_signal_family(self.signal_family, pressure_score=pressure_score)

        elapsed = time.time() - start
        print("\nEXPLORATORY ENTRY SIGNAL GENERATED")
        print(f"  Side: {side.upper()}")
        print(f"  Time: {row.name}")
        print(f"  Pressure score: {pressure_score}")
        print(f"  Role: {trade.entry_role.upper()}")
        print(f"  Risk multiplier: {trade.entry_risk_multiplier:.2f}x")
        print(f"Elapsed: {elapsed:.4f}s")

        return {
            "side": side,
            "score": pressure_score,
            "trade": trade,
            "trade_regime": regime_score,
            "regime_class": regime_class,
            "entry_threshold": threshold,
            "entry_risk_multiplier": trade.entry_risk_multiplier,
            "entry_role": trade.entry_role,
            "entry_priority": trade.entry_priority,
            "signal_family": self.signal_family,
        }
