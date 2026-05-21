"""Controls configured add-to-winner levels and incremental position sizing."""

import time

from config import AppConfig


class PyramidingEngine:
    """
    Configured add-to-winner logic.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        self.levels = self.config.require("strategy", "pyramiding", "levels")

    def check_pyramiding(self, price, entry_price, R, current_level):
        start = time.time()

        print("\nChecking pyramiding levels...")

        new_level = current_level

        for level_config in self.levels:
            level = level_config["level"]
            required_previous_level = level - 1
            trigger_price = entry_price + (level_config["r_multiple"] * R)

            if current_level == required_previous_level and price >= trigger_price:
                new_level = level
                print(
                    f" Triggered Level {level} "
                    f"(>= +{level_config['r_multiple']}R)"
                )
                break

        if new_level == current_level:
            print("No pyramiding condition met")

        print(f"  Price: {price:.2f}")
        print(f"  Entry: {entry_price:.2f}")
        print(f"  R: {R:.2f}")
        print(f"  Level: {current_level} -> {new_level}")

        elapsed = time.time() - start
        print(f"Elapsed: {elapsed:.4f}s")

        return new_level

    def get_pyramid_size(self, base_size, level):
        print("\nCalculating pyramid position size...")

        for level_config in self.levels:
            if level_config["level"] == level:
                size = base_size * level_config["size_fraction"]
                print(f"Add size (Level {level}): {size:.4f}")
                return size

        print("No additional position")
        return 0


def check_pyramiding(price, entry_price, R, current_level, config=None):
    return PyramidingEngine(config=config).check_pyramiding(
        price=price,
        entry_price=entry_price,
        R=R,
        current_level=current_level
    )


def get_pyramid_size(base_size, level, config=None):
    return PyramidingEngine(config=config).get_pyramid_size(base_size, level)
