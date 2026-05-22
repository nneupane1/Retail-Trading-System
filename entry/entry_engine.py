"""Converts a scored setup into a Trade object when configured entry rules are satisfied."""

import time

from common.debug import debug_print as print
from config import AppConfig
from simulation.trade import Trade


class EntryEngine:
    """
    Converts score and bias into an executable Trade object.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        self.entry_threshold = self.config.require("entry", "score_threshold")

    def generate_entry(self, row, score, bias):
        start = time.time()

        print("\nRunning entry engine...")

        # Only trade in bullish direction (for now)
        if bias != "bullish":
            print("No entry: bias not bullish")
            return None

        # Score check
        if score < self.entry_threshold:
            print(f"No entry: score too low ({score} < {self.entry_threshold})")
            return None

        # Breakout event must be present (core rule)
        if not row["breakout"]:
            print("No entry: breakout event not confirmed")
            return None

        # Optional: allow retest as alternative (if you want later)
        # if not (row["breakout"] or row["retest"]):
        #    return None

        # Create trade
        trade = Trade(row, score, config=self.config)

        print("\nENTRY SIGNAL GENERATED")
        print(f"  Time: {row.name}")
        print(f"  Price: {row['close']:.2f}")
        print(f"  Score: {score}")
        print(f"  Bias: {bias}")

        elapsed = time.time() - start
        print(f"Elapsed: {elapsed:.4f}s")

        return trade


def generate_entry(row, score, bias, config=None):
    return EntryEngine(config=config).generate_entry(row, score, bias)
