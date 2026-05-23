"""Controls configured add-to-winner levels and incremental position sizing."""

import time

from common.debug import debug_print as print
from config import AppConfig


class PyramidingEngine:
    """
    Configured add-to-winner logic.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        self.levels = self.config.require("strategy", "pyramiding", "levels")
        self.levels_by_level = {
            level_config["level"]: level_config
            for level_config in self.levels
        }
        self.max_total_risk_multiple = self.config.require(
            "strategy",
            "pyramiding",
            "max_total_risk_multiple"
        )
        getter = getattr(self.config, "get", None)
        if callable(getter):
            self.quality_gate = getter(
                "strategy",
                "pyramiding",
                "quality_gate",
                default={},
            ) or {}
        else:
            try:
                self.quality_gate = self.config.require(
                    "strategy",
                    "pyramiding",
                    "quality_gate",
                ) or {}
            except Exception:
                self.quality_gate = {}

    def check_pyramiding(
        self,
        price,
        entry_price,
        R,
        current_level,
        trend_ok=True,
        previous_price=None,
        side="long",
    ):
        start = time.time()
        side = str(side).lower()

        print("\nChecking pyramiding levels...")

        if not trend_ok:
            print("Pyramiding blocked: trend health does not support adding")
            print(f"Elapsed: {time.time() - start:.4f}s")
            return current_level

        if previous_price is None:
            print("Pyramiding blocked: previous price unavailable for event trigger")
            print(f"Elapsed: {time.time() - start:.4f}s")
            return current_level

        new_level = current_level

        for level_config in self.levels:
            level = level_config["level"]
            required_previous_level = level - 1
            if side == "short":
                trigger_price = entry_price - (level_config["r_multiple"] * R)
                crossed_level = previous_price > trigger_price >= price
            else:
                trigger_price = entry_price + (level_config["r_multiple"] * R)
                crossed_level = previous_price < trigger_price <= price

            if current_level == required_previous_level and crossed_level:
                new_level = level
                print(
                    f" Triggered Level {level} "
                    f"(crossed {'-' if side == 'short' else '+'}{level_config['r_multiple']}R)"
                )
                break

        if new_level == current_level:
            print("No pyramiding condition met")

        print(f"  Side: {side.upper()}")
        print(f"  Previous price: {previous_price:.2f}")
        print(f"  Price: {price:.2f}")
        print(f"  Entry: {entry_price:.2f}")
        print(f"  R: {R:.2f}")
        print(f"  Level: {current_level} -> {new_level}")

        elapsed = time.time() - start
        print(f"Elapsed: {elapsed:.4f}s")

        return new_level

    def _resolved_size_fraction(self, level, quality_gate_passed):
        level_config = self.levels_by_level.get(level)
        if not level_config:
            return 0

        size_fraction = float(level_config["size_fraction"])
        if quality_gate_passed and self.quality_gate.get("enabled", False):
            multipliers = self.quality_gate.get(
                "size_fraction_multipliers_by_level",
                {},
            ) or {}
            multiplier = float(multipliers.get(str(level), multipliers.get(level, 1.0)))
            size_fraction *= multiplier

        return size_fraction

    def get_pyramid_size(self, base_size, level, quality_gate_passed=False):
        print("\nCalculating pyramid position size...")

        level_config = self.levels_by_level.get(level)
        if level_config:
            size_fraction = self._resolved_size_fraction(level, quality_gate_passed)
            size = base_size * size_fraction
            print(f"Add size (Level {level}): {size:.4f}")
            return size

        print("No additional position")
        return 0

    def qualifies_for_pyramiding(self, row, trade):
        quality_gate = self.quality_gate
        if not quality_gate.get("enabled", False):
            return True

        if trade is None or not getattr(trade, "R", 0):
            print("Pyramiding blocked: missing trade context for quality gate")
            return False

        side = getattr(trade, "side", "long")
        body_strength = float(row.get("body_strength", 0.0))
        close_position = float(row.get("close_position", 0.0))
        if side == "short":
            wick_ratio = float(row.get("lower_wick_ratio", float("inf")))
            wick_key = "lower_wick_max"
            wick_threshold = quality_gate.get(
                wick_key,
                quality_gate.get("upper_wick_max", float("inf")),
            )
            strong_close = close_position <= (
                1.0 - float(quality_gate.get("close_position_min", 0.0))
            )
            open_r_multiple = (float(trade.entry_price) - float(row["close"])) / float(trade.R)
        else:
            wick_ratio = float(row.get("upper_wick_ratio", float("inf")))
            wick_threshold = quality_gate.get("upper_wick_max", float("inf"))
            strong_close = close_position >= quality_gate.get("close_position_min", 0.0)
            open_r_multiple = (float(row["close"]) - float(trade.entry_price)) / float(trade.R)

        strong_body = body_strength >= quality_gate.get("body_strength_min", 0.0)
        clean_wick = wick_ratio <= wick_threshold
        min_open_r_multiple = quality_gate.get("min_open_r_multiple", 0.0)
        min_confirmations = int(quality_gate.get("min_confirmations", 0))

        confirmation_count = sum([
            strong_body,
            clean_wick,
            strong_close,
        ])
        qualifies = (
            open_r_multiple >= min_open_r_multiple
            and confirmation_count >= min_confirmations
        )

        if qualifies:
            print("Pyramiding quality gate PASSED")
        else:
            print("Pyramiding blocked: quality gate failed")

        print(f"  Side: {side.upper()}")
        print(f"  Open R multiple: {open_r_multiple:.2f}")
        print(f"  Body strength: {body_strength:.2f} {'PASS' if strong_body else 'FAIL'}")
        print(f"  Wick ratio: {wick_ratio:.2f} {'PASS' if clean_wick else 'FAIL'}")
        print(f"  Close position: {close_position:.2f} {'PASS' if strong_close else 'FAIL'}")
        print(f"  Confirmation count: {confirmation_count}/3 (need {min_confirmations})")

        return qualifies

    def _resolved_max_total_risk_multiple(self, quality_gate_passed):
        if quality_gate_passed and self.quality_gate.get("enabled", False):
            return self.quality_gate.get(
                "max_total_risk_multiple",
                self.max_total_risk_multiple,
            )
        return self.max_total_risk_multiple

    def cap_add_size_by_risk(
        self,
        add_size,
        add_price,
        stop_price,
        current_total_risk,
        equity,
        risk_per_trade,
        quality_gate_passed=False,
    ):
        max_total_risk_multiple = self._resolved_max_total_risk_multiple(
            quality_gate_passed=quality_gate_passed,
        )
        max_total_risk = equity * risk_per_trade * max_total_risk_multiple
        remaining = max_total_risk - current_total_risk

        if remaining <= 0:
            print("Pyramiding blocked: risk budget exhausted")
            return 0

        risk_per_unit = abs(add_price - stop_price)
        if risk_per_unit == 0:
            print("Pyramiding blocked: invalid stop distance")
            return 0

        max_add_size = remaining / risk_per_unit
        capped = min(add_size, max_add_size)

        if capped < add_size:
            print(
                "Pyramiding capped by risk budget "
                f"({capped:.4f} <= {add_size:.4f})"
            )

        return max(0, capped)


def check_pyramiding(
    price,
    entry_price,
    R,
    current_level,
    trend_ok=True,
    previous_price=None,
    side="long",
    config=None
):
    return PyramidingEngine(config=config).check_pyramiding(
        price=price,
        entry_price=entry_price,
        R=R,
        current_level=current_level,
        trend_ok=trend_ok,
        previous_price=previous_price,
        side=side,
    )


def get_pyramid_size(base_size, level, config=None):
    return PyramidingEngine(config=config).get_pyramid_size(base_size, level)
