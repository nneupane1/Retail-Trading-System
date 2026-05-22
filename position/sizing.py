"""Calculates risk-based position sizes from account equity and stop distance."""

import time

from common.debug import debug_print as print
from config import AppConfig


class PositionSizer:
    """
    Risk-based position sizing.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        self.min_stop_distance_ratio = self.config.get(
            "position",
            "min_stop_distance_ratio",
            default=0.0
        )
        self.min_stop_distance_absolute = self.config.get(
            "position",
            "min_stop_distance_absolute",
            default=0.0
        )
        self.max_position_size_units = self.config.get(
            "position",
            "max_position_size_units",
            default=None
        )
        self.max_notional_equity_multiple = self.config.get(
            "position",
            "max_notional_equity_multiple",
            default=None
        )

    def _minimum_stop_distance(self, entry_price):
        return max(
            abs(entry_price) * self.min_stop_distance_ratio,
            self.min_stop_distance_absolute
        )

    def calculate(
        self,
        equity,
        risk_per_trade,
        entry_price,
        stop_price
    ):
        start = time.time()

        print("\nCalculating position size...")

        # absolute risk in $ terms
        risk_amount = equity * risk_per_trade

        # distance between entry and stop
        risk_per_unit = abs(entry_price - stop_price)
        minimum_stop_distance = self._minimum_stop_distance(entry_price)

        if risk_per_unit == 0:
            print("Invalid stop distance (zero)")
            return 0

        if risk_per_unit < minimum_stop_distance:
            print("Invalid stop distance (too small for safe sizing)")
            print(f"  Risk per unit: {risk_per_unit:.6f}")
            print(f"  Minimum required: {minimum_stop_distance:.6f}")
            return 0

        # raw size from risk model
        position_size = risk_amount / risk_per_unit
        uncapped_position_size = position_size

        if self.max_position_size_units is not None:
            position_size = min(position_size, self.max_position_size_units)

        if (
            self.max_notional_equity_multiple is not None and
            entry_price != 0
        ):
            max_notional = equity * self.max_notional_equity_multiple
            max_size_from_notional = max_notional / abs(entry_price)
            position_size = min(position_size, max_size_from_notional)

        # debug info
        print(f"  Equity: {equity:.2f}")
        print(f"  Risk per trade: {risk_per_trade * 100:.2f}%")
        print(f"  Risk amount: {risk_amount:.2f}")

        print(f"\n  Entry: {entry_price:.2f}")
        print(f"  Stop:  {stop_price:.2f}")
        print(f"  Risk per unit: {risk_per_unit:.2f}")
        print(f"  Minimum stop distance: {minimum_stop_distance:.6f}")

        print(f"\nPosition size: {position_size:.4f} units")

        if position_size < uncapped_position_size:
            print(f"  Raw position size: {uncapped_position_size:.4f} units")
            print("  Position size capped by configured safety limit")

        elapsed = time.time() - start
        print(f"Elapsed: {elapsed:.4f}s")

        return position_size


def calculate_position_size(
    equity,
    risk_per_trade,
    entry_price,
    stop_price,
    config=None
):
    return PositionSizer(config=config).calculate(
        equity=equity,
        risk_per_trade=risk_per_trade,
        entry_price=entry_price,
        stop_price=stop_price
    )
