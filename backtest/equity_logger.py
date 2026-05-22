"""Writes the backtest equity curve to CSV so account state can be audited after each candle."""

import os
import csv
import time

from common.debug import debug_print as print
from config import AppConfig


class EquityLogger:
    """
    Tracks equity curve over time.
    """

    def __init__(self, filepath=None, config=None):

        print("\nInitializing Equity Logger...")

        self.config = config or AppConfig.load()
        output_dir = self.config.require("backtest", "output_dir")
        self.filepath = filepath or os.path.join(output_dir, "equity.csv")

        directory = os.path.dirname(self.filepath)
        if directory:
            os.makedirs(directory, exist_ok=True)

        with open(self.filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "equity"
            ])

        print(f"Equity logger ready -> {self.filepath}")

    # log equity at each update
    def log(self, timestamp, equity):

        with open(self.filepath, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, equity])
