import os
import csv
import time


class EquityLogger:
    """
    Tracks equity curve over time.
    """

    def __init__(self, filepath="backtest/output/equity.csv"):

        print("\n📈 Initializing Equity Logger...")

        self.filepath = filepath

        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(self.filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "equity"
            ])

        print(f"✅ Equity logger ready → {self.filepath}")

    # ✅ log equity at each update
    def log(self, timestamp, equity):

        with open(self.filepath, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, equity])
