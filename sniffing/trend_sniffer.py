"""Checks whether an open trend remains healthy enough to keep holding the trade."""

import time

from common.debug import debug_print as print
from config import AppConfig


class TrendSniffer:
    """
    Determines if the active trend remains healthy enough to hold and how the
    protective stop should evolve for the next candle.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        self.thresholds = self.config.require("strategy", "sniffing")
        fast_ema_period = self.config.require("features", "ema_periods", "fast")
        slow_ema_period = self.config.require("features", "ema_periods", "slow")
        self.fast_ema_column = f"ema{fast_ema_period}"
        self.slow_ema_column = f"ema{slow_ema_period}"
        self.lower_close_position_max = self.thresholds.get(
            "close_position_max",
            1.0 - self.thresholds["close_position_min"],
        )
        self.lower_wick_max = self.thresholds.get(
            "lower_wick_max",
            self.thresholds["upper_wick_max"],
        )
        self.require_short_vwap_alignment = bool(
            self.thresholds.get("require_short_vwap_alignment", True)
        )
        self.side_overrides = {
            str(side).lower(): dict(values or {})
            for side, values in (self.thresholds.get("by_side", {}) or {}).items()
        }
        self.support_alpha_overrides = dict(
            self.thresholds.get("support_alpha", {}) or {}
        )
        self.support_alpha_side_overrides = {
            str(side).lower(): dict(values or {})
            for side, values in (
                self.support_alpha_overrides.get("by_side", {}) or {}
            ).items()
        }
        self.trailing_thresholds = dict(self.thresholds.get("trailing", {}) or {})
        self.trailing_side_overrides = {
            str(side).lower(): dict(values or {})
            for side, values in (
                self.trailing_thresholds.get("by_side", {}) or {}
            ).items()
        }

    def _side_value(self, side, key, default, support_alpha=False):
        value = self.side_overrides.get(side, {}).get(key, default)
        if support_alpha:
            if key in self.support_alpha_overrides:
                value = self.support_alpha_overrides[key]
            if key in self.support_alpha_side_overrides.get(side, {}):
                value = self.support_alpha_side_overrides[side][key]
        return value

    def _trailing_value(self, side, key, default):
        value = self.trailing_thresholds.get(key, default)
        if key in self.trailing_side_overrides.get(side, {}):
            value = self.trailing_side_overrides[side][key]
        return value

    @staticmethod
    def _price_epsilon(price):
        return max(abs(float(price)) * 1e-6, 1e-9)

    def _compute_open_r_multiple(self, trade, price):
        if trade is None or not getattr(trade, "R", 0):
            return None
        if getattr(trade, "side", "long") == "short":
            return (trade.entry_price - price) / trade.R
        return (price - trade.entry_price) / trade.R

    def _momentum_score(self, row, side):
        body_strength = float(row.get("body_strength", 0.0) or 0.0)
        close_position = float(row.get("close_position", 0.0) or 0.0)
        upper_wick_ratio = float(row.get("upper_wick_ratio", 0.0) or 0.0)
        lower_wick_ratio = float(row.get("lower_wick_ratio", 0.0) or 0.0)
        vwap_distance_ratio = float(row.get("vwap_distance_ratio", 0.0) or 0.0)
        ema_gap_ratio = float(row.get("ema_gap_ratio", 0.0) or 0.0)
        macd_hist = float(row.get("macd_hist", 0.0) or 0.0)

        strong_body_min = self._trailing_value(side, "strong_body_min", 1.0)
        clean_wick_max = self._trailing_value(side, "clean_wick_max", 1.0)
        min_vwap_distance = self._trailing_value(side, "min_vwap_distance", 0.0)
        min_ema_gap = self._trailing_value(side, "min_ema_gap", 0.0)

        if side == "short":
            signals = [
                body_strength >= strong_body_min,
                close_position <= self._trailing_value(side, "strong_close_position_max", 0.35),
                lower_wick_ratio <= clean_wick_max,
                vwap_distance_ratio <= -abs(min_vwap_distance),
                ema_gap_ratio <= -abs(min_ema_gap),
                macd_hist <= self._trailing_value(side, "strong_macd_hist_max", 0.0),
            ]
        else:
            signals = [
                body_strength >= strong_body_min,
                close_position >= self._trailing_value(side, "strong_close_position_min", 0.65),
                upper_wick_ratio <= clean_wick_max,
                vwap_distance_ratio >= min_vwap_distance,
                ema_gap_ratio >= min_ema_gap,
                macd_hist >= self._trailing_value(side, "strong_macd_hist_min", 0.0),
            ]

        return sum(bool(signal) for signal in signals)

    def _decay_score(self, row, side):
        body_strength = float(row.get("body_strength", 0.0) or 0.0)
        close_position = float(row.get("close_position", 0.0) or 0.0)
        upper_wick_ratio = float(row.get("upper_wick_ratio", 0.0) or 0.0)
        lower_wick_ratio = float(row.get("lower_wick_ratio", 0.0) or 0.0)
        vwap_distance_ratio = float(row.get("vwap_distance_ratio", 0.0) or 0.0)
        ema_gap_ratio = float(row.get("ema_gap_ratio", 0.0) or 0.0)
        macd_hist = float(row.get("macd_hist", 0.0) or 0.0)

        body_decay_max = self._trailing_value(side, "body_decay_max", 0.8)
        wick_decay_min = self._trailing_value(side, "wick_decay_min", 1.5)
        vwap_decay_threshold = abs(self._trailing_value(side, "vwap_decay_threshold", 0.0015))
        ema_gap_decay_threshold = abs(self._trailing_value(side, "ema_gap_decay_threshold", 0.0010))
        macd_decay_threshold = abs(self._trailing_value(side, "macd_decay_threshold", 0.0))

        if side == "short":
            signals = [
                body_strength <= body_decay_max,
                lower_wick_ratio >= wick_decay_min,
                close_position >= self._trailing_value(side, "decay_close_position_min", 0.55),
                vwap_distance_ratio >= -vwap_decay_threshold,
                ema_gap_ratio >= -ema_gap_decay_threshold,
                macd_hist >= -macd_decay_threshold,
            ]
        else:
            signals = [
                body_strength <= body_decay_max,
                upper_wick_ratio >= wick_decay_min,
                close_position <= self._trailing_value(side, "decay_close_position_max", 0.45),
                vwap_distance_ratio <= vwap_decay_threshold,
                ema_gap_ratio <= ema_gap_decay_threshold,
                macd_hist <= macd_decay_threshold,
            ]

        return sum(bool(signal) for signal in signals)

    def _select_anchor_column(self, side, state):
        if side == "short":
            expansion_default = self.fast_ema_column
        else:
            expansion_default = self.slow_ema_column

        if state == "expansion":
            configured = self._trailing_value(side, "expansion_anchor", expansion_default)
            return self.slow_ema_column if configured == "slow_ema" else self.fast_ema_column

        if state == "decay":
            configured = self._trailing_value(side, "decay_anchor", self.fast_ema_column)
            return self.slow_ema_column if configured == "slow_ema" else self.fast_ema_column

        configured = self._trailing_value(side, "confirmation_anchor", self.fast_ema_column)
        return self.slow_ema_column if configured == "slow_ema" else self.fast_ema_column

    def _classify_state(self, side, open_r_multiple, momentum_score, decay_score, anchor_aligned):
        if open_r_multiple is None:
            return "init"

        force_exit_threshold = int(
            self._trailing_value(
                side,
                "force_exit_decay_signal_threshold",
                3 if side == "short" else 4,
            )
        )
        if decay_score >= force_exit_threshold:
            return "exit"

        decay_threshold = int(
            self._trailing_value(side, "decay_signal_threshold", 2)
        )
        if decay_score >= decay_threshold:
            return "decay"

        init_max_r = float(
            self._trailing_value(side, "init_max_r", 0.35 if side == "short" else 0.5)
        )
        if open_r_multiple < init_max_r:
            return "init"

        confirmation_max_r = float(
            self._trailing_value(side, "confirmation_max_r", 1.0 if side == "short" else 1.5)
        )
        expansion_min_momentum_signals = int(
            self._trailing_value(side, "expansion_min_momentum_signals", 3 if side == "short" else 4)
        )
        if open_r_multiple < confirmation_max_r or momentum_score < expansion_min_momentum_signals:
            return "confirmation"

        return "expansion"

    def _atr_buffer(self, side, state, atr_value, trade):
        if atr_value <= 0:
            return abs(float(getattr(trade, "R", 0.0) or 0.0)) * 0.15

        defaults = {
            "init": 1.0 if side == "short" else 1.2,
            "confirmation": 0.7 if side == "short" else 0.9,
            "expansion": 1.0 if side == "short" else 1.8,
            "decay": 0.25 if side == "short" else 0.35,
            "exit": 0.10 if side == "short" else 0.15,
        }
        multiplier = float(
            self._trailing_value(side, f"{state}_atr_buffer", defaults[state])
        )
        return atr_value * multiplier

    def _clamp_proposed_stop(self, side, proposed_stop, price):
        epsilon = self._price_epsilon(price)
        if side == "short":
            return max(float(proposed_stop), float(price) + epsilon)
        return min(float(proposed_stop), float(price) - epsilon)

    def _proposed_stop(self, row, trade, side, state, anchor_column):
        stop_column = getattr(trade, "stop_column", "")
        current_stop = float(
            getattr(
                trade,
                "active_stop",
                getattr(trade, "stop", row.get(stop_column, 0.0)),
            )
        )
        structure_stop = float(
            row.get(stop_column, getattr(trade, "stop", current_stop))
            or current_stop
        )
        price = float(row["close"])
        atr_value = float(row.get("atr", 0.0) or 0.0)
        vwap_value = float(row.get("session_vwap", price) or price)
        anchor_price = float(
            row.get(anchor_column, row.get(self.fast_ema_column, price)) or price
        )
        buffer = self._atr_buffer(side, state, atr_value, trade)

        if side == "short":
            if state == "init":
                candidate = current_stop
            elif state == "confirmation":
                candidate = min(structure_stop, float(row[self.fast_ema_column]) + buffer)
            elif state == "expansion":
                candidate = min(structure_stop, anchor_price + buffer)
            elif state == "decay":
                candidate = min(
                    structure_stop,
                    float(row[self.fast_ema_column]) + buffer,
                    vwap_value + (buffer * 0.5),
                )
            else:
                candidate = min(
                    structure_stop,
                    float(row[self.fast_ema_column]) + buffer,
                    vwap_value + (buffer * 0.25),
                )

            candidate = self._clamp_proposed_stop(side, candidate, price)
            return min(current_stop, candidate)

        if state == "init":
            candidate = current_stop
        elif state == "confirmation":
            candidate = max(structure_stop, float(row[self.fast_ema_column]) - buffer)
        elif state == "expansion":
            candidate = max(structure_stop, anchor_price - buffer)
        elif state == "decay":
            candidate = max(
                structure_stop,
                float(row[self.fast_ema_column]) - buffer,
                vwap_value - (buffer * 0.5),
            )
        else:
            candidate = max(
                structure_stop,
                float(row[self.fast_ema_column]) - buffer,
                vwap_value - (buffer * 0.25),
            )

        candidate = self._clamp_proposed_stop(side, candidate, price)
        return max(current_stop, candidate)

    def evaluate(self, row, trade=None):
        start = time.time()

        print("\nSniffing trend strength...")

        side = getattr(trade, "side", "long") if trade is not None else "long"
        entry_risk_multiplier = (
            float(getattr(trade, "entry_risk_multiplier", 1.0) or 1.0)
            if trade is not None
            else 1.0
        )
        is_support_alpha = entry_risk_multiplier < 1.0
        price = float(row["close"])
        body_strength = float(row.get("body_strength", 0.0) or 0.0)
        close_pos = float(row.get("close_position", 0.0) or 0.0)
        wick_metric = "upper_wick_ratio" if side == "long" else "lower_wick_ratio"
        wick_value = float(row.get(wick_metric, 0.0) or 0.0)
        wick_threshold = (
            self._side_value(
                side,
                "upper_wick_max",
                self.thresholds["upper_wick_max"],
                support_alpha=is_support_alpha,
            )
            if side == "long"
            else self._side_value(
                side,
                "lower_wick_max",
                self.lower_wick_max,
                support_alpha=is_support_alpha,
            )
        )
        min_confirmations = self._side_value(
            side,
            "min_confirmations",
            self.thresholds.get("min_confirmations", 1),
            support_alpha=is_support_alpha,
        )

        open_r_multiple = self._compute_open_r_multiple(trade, price)
        relax_after_r = self._side_value(
            side,
            "relax_after_r",
            self.thresholds.get("relax_after_r"),
            support_alpha=is_support_alpha,
        )
        relaxed_min_confirmations = self._side_value(
            side,
            "relaxed_min_confirmations",
            self.thresholds.get("relaxed_min_confirmations", min_confirmations),
            support_alpha=is_support_alpha,
        )
        if open_r_multiple is not None and relax_after_r is not None and open_r_multiple >= relax_after_r:
            min_confirmations = relaxed_min_confirmations

        pre_state_anchor_column = self.fast_ema_column
        if trade is not None:
            pre_state_anchor_column = self._select_anchor_column(side, "confirmation")
        ema_value = float(row.get(pre_state_anchor_column, price) or price)

        if side == "short":
            anchor_aligned = price < ema_value
            strong_close = close_pos < self._side_value(
                side,
                "close_position_max",
                self.lower_close_position_max,
                support_alpha=is_support_alpha,
            )
            vwap_value = float(row.get("session_vwap", price) or price)
            require_short_vwap_alignment = self._side_value(
                side,
                "require_short_vwap_alignment",
                self.require_short_vwap_alignment,
                support_alpha=is_support_alpha,
            )
            vwap_aligned = (price < vwap_value) if require_short_vwap_alignment else True
        else:
            anchor_aligned = price > ema_value
            strong_close = close_pos > self._side_value(
                side,
                "close_position_min",
                self.thresholds["close_position_min"],
                support_alpha=is_support_alpha,
            )
            vwap_aligned = True
            vwap_value = float(row.get("session_vwap", price) or price)
            require_short_vwap_alignment = False

        strong_body = body_strength > self._side_value(
            side,
            "body_strength_min",
            self.thresholds["body_strength_min"],
            support_alpha=is_support_alpha,
        )
        clean_wick = wick_value < wick_threshold
        confirmation_count = sum([strong_body, clean_wick, strong_close])
        trend_alive = anchor_aligned and vwap_aligned and confirmation_count >= min_confirmations

        momentum_score = self._momentum_score(row, side)
        decay_score = self._decay_score(row, side)
        state = self._classify_state(
            side=side,
            open_r_multiple=open_r_multiple,
            momentum_score=momentum_score,
            decay_score=decay_score,
            anchor_aligned=anchor_aligned,
        )
        anchor_column = self._select_anchor_column(side, state)
        anchor_price = float(
            row.get(anchor_column, row.get(self.fast_ema_column, price)) or price
        )
        if side == "short":
            anchor_aligned = price < anchor_price
        else:
            anchor_aligned = price > anchor_price
        trend_alive = anchor_aligned and vwap_aligned and confirmation_count >= min_confirmations
        if state != "exit" and open_r_multiple is not None and open_r_multiple > 0 and not anchor_aligned:
            state = "exit"
        proposed_stop = (
            self._proposed_stop(
                row=row,
                trade=trade,
                side=side,
                state=state,
                anchor_column=anchor_column,
            )
            if trade is not None
            else None
        )
        should_exit = state == "exit" or not trend_alive

        print(f"  Side: {side.upper()}")
        print(f"  Price: {price:.2f}")
        print(f"  Anchor EMA ({anchor_column}): {anchor_price:.2f}")
        if is_support_alpha:
            print("  Support alpha mode: YES")
        if side == "short":
            print(f"  Session VWAP: {vwap_value:.2f}")

        print(f"\n  State: {state.upper()}")
        print(f"  Anchor aligned: {'PASS' if anchor_aligned else 'FAIL'}")
        if side == "short" and require_short_vwap_alignment:
            print(f"  Below session VWAP: {'PASS' if vwap_aligned else 'FAIL'}")
        print(f"  Body strength: {body_strength:.2f} {'PASS' if strong_body else 'FAIL'}")
        print(f"  {wick_metric}: {wick_value:.2f} {'PASS' if clean_wick else 'FAIL'}")
        print(f"  Close position: {close_pos:.2f} {'PASS' if strong_close else 'FAIL'}")
        if open_r_multiple is not None:
            print(f"  Open R multiple: {open_r_multiple:.2f}")
        print(f"  Momentum score: {momentum_score}")
        print(f"  Decay score: {decay_score}")
        print(
            "  Confirmation count: "
            f"{confirmation_count}/3 "
            f"(need {min_confirmations})"
        )
        if proposed_stop is not None:
            print(f"  Proposed trailing stop: {proposed_stop:.2f}")

        if should_exit:
            print("\nTrend weakening -> EXIT")
        elif state == "decay":
            print("\nTrend decaying -> HOLD, tighten stop")
        else:
            print("\nTrend is alive -> HOLD")

        elapsed = time.time() - start
        print(f"Elapsed: {elapsed:.4f}s")

        return {
            "trend_alive": trend_alive,
            "should_exit": should_exit,
            "state": state,
            "anchor_column": anchor_column,
            "anchor_price": anchor_price,
            "open_r_multiple": open_r_multiple,
            "momentum_score": momentum_score,
            "decay_score": decay_score,
            "proposed_stop": proposed_stop,
            "is_support_alpha": is_support_alpha,
            "allow_pyramiding": state in {"confirmation", "expansion"},
        }

    def is_trend_alive(self, row, trade=None):
        return self.evaluate(row, trade=trade)["trend_alive"]


def is_trend_alive(row, config=None):
    return TrendSniffer(config=config).is_trend_alive(row)
