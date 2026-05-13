import os
import csv
import time


class LiveTradeLogger:
    """
    Logs trades from live simulation into CSV.

    Similar to backtest logger but stored separately.
    """

    def __init__(self, filepath="live_sim/output/trades.csv"):

        print("\n📝 Initializing LIVE Trade Logger...")

        self.filepath = filepath

        # ✅ ensure folder exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        # ✅ create file with header (only once)
        if not os.path.exists(self.filepath):
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

        print(f"✅ Live logger ready → {self.filepath}")

    # ✅ ------------------------------------------
    # Log completed trade
    # ✅ ------------------------------------------

    def log_trade(self, trade):

        print("\n📝 Logging LIVE trade...")

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

        print("✅ LIVE trade logged")

        print(f"⏱ Time taken: {time.time() - start:.4f}s")
