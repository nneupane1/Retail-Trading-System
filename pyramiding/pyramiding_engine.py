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

    def check_pyramiding(
        self,
        price,
        entry_price,
        R,
        current_level,
        trend_ok=True,
        previous_price=None
    ):
        start = time.time()

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
            trigger_price = entry_price + (level_config["r_multiple"] * R)
            crossed_level = previous_price < trigger_price <= price

            if current_level == required_previous_level and crossed_level:
                new_level = level
                print(
                    f" Triggered Level {level} "
                    f"(crossed +{level_config['r_multiple']}R)"
                )
                break

        if new_level == current_level:
            print("No pyramiding condition met")

        print(f"  Previous price: {previous_price:.2f}")
        print(f"  Price: {price:.2f}")
        print(f"  Entry: {entry_price:.2f}")
        print(f"  R: {R:.2f}")
        print(f"  Level: {current_level} -> {new_level}")

        elapsed = time.time() - start
        print(f"Elapsed: {elapsed:.4f}s")

        return new_level

    def get_pyramid_size(self, base_size, level):
        print("\nCalculating pyramid position size...")

        level_config = self.levels_by_level.get(level)
        if level_config:
            size = base_size * level_config["size_fraction"]
            print(f"Add size (Level {level}): {size:.4f}")
            return size

        print("No additional position")
        return 0

    def cap_add_size_by_risk(
        self,
        add_size,
        add_price,
        stop_price,
        current_total_risk,
        equity,
        risk_per_trade
    ):
        """
        Risk-budgeted pyramiding.

        Caps the requested add size so the total worst-case loss to the shared
        stop does not exceed:

            equity * risk_per_trade * max_total_risk_multiple
        """

        max_total_risk = equity * risk_per_trade * self.max_total_risk_multiple
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
    config=None
):
    return PyramidingEngine(config=config).check_pyramiding(
        price=price,
        entry_price=entry_price,
        R=R,
        current_level=current_level,
        trend_ok=trend_ok,
        previous_price=previous_price
    )


def get_pyramid_size(base_size, level, config=None):
    return PyramidingEngine(config=config).get_pyramid_size(base_size, level)
