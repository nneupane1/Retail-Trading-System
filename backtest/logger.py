import os
import csv
import time


class TradeLogger:
    """
    Logs completed trades into CSV.

    Stores:
    - entry/exit info
    - pnl
    - R multiple
    - all conditions (WHY trade was taken)
    """

    def __init__(self, filepath="backtest/output/trades.csv"):

        print("\n📝 Initializing Trade Logger...")

        self.filepath = filepath

        # ✅ ensure folder exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        # ✅ create file with header
        with open(self.filepath, "w", newline="") as f:
            writer = csv.writer(f)

            writer.writerow([
                "entry_time",
                "exit_time",
                "entry_price",
                "exit_price",
                "pnl",
                "pnl_R",
                "score",
                "body_strength",
                "close_position",
                "upper_wick_ratio",
                "compression",
                "breakout"
            ])

        print(f"✅ Logger ready → {self.filepath}")

    # ✅ --------------------------------------------------
    # Log a completed trade
    # ✅ --------------------------------------------------

    def log_trade(self, trade):

        print("\n📝 Logging trade...")

        start = time.time()

        with open(self.filepath, "a", newline="") as f:
            writer = csv.writer(f)

            writer.writerow([
                trade.entry_time,
                trade.exit_time,
                trade.entry_price,
                trade.exit_price,
                trade.pnl,
                trade.pnl_R,
                trade.conditions.get("score"),
                trade.conditions.get("body_strength"),
                trade.conditions.get("close_position"),
                trade.conditions.get("upper_wick_ratio"),
                trade.conditions.get("compression"),
                trade.conditions.get("breakout")
            ])

        print("✅ Trade logged successfully")

        elapsed = time.time() - start
        print(f"⏱ Time taken: {elapsed:.4f}s")
``
