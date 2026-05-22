"""Writes completed backtest trades to CSV with entry, exit, PnL, and setup context."""

import os
import csv
import time

from common.debug import debug_print as print
from config import AppConfig


class TradeLogger:
    """
    Logs completed trades into CSV.

    Stores:
    - entry/exit info
    - pnl
    - R multiple
    - all conditions (WHY trade was taken)
    """

    def __init__(self, filepath=None, config=None):

        print("\nInitializing Trade Logger...")

        self.config = config or AppConfig.load()
        output_dir = self.config.require("backtest", "output_dir")
        self.filepath = filepath or os.path.join(output_dir, "trades.csv")

        # ensure folder exists
        directory = os.path.dirname(self.filepath)
        if directory:
            os.makedirs(directory, exist_ok=True)

        # create file with header
        with open(self.filepath, "w", newline="") as f:
            writer = csv.writer(f)

            writer.writerow([
                "entry_time",
                "exit_time",
                "entry_price",
                "exit_price",
                "pnl",
                "pnl_R",
                "pnl_R_total",
                "pnl_R_initial",
                "initial_risk_amount",
                "total_risk_amount",
                "score",
                "body_strength",
                "close_position",
                "upper_wick_ratio",
                "compression",
                "breakout"
            ])

        print(f"Logger ready -> {self.filepath}")

    # --------------------------------------------------
    # Log a completed trade
    # --------------------------------------------------

    def log_trade(self, trade):

        print("\nLogging trade...")

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
                trade.pnl_R_total,
                trade.pnl_R_initial,
                trade.initial_risk_amount,
                trade.total_risk_amount,
                trade.conditions.get("score"),
                trade.conditions.get("body_strength"),
                trade.conditions.get("close_position"),
                trade.conditions.get("upper_wick_ratio"),
                trade.conditions.get("compression"),
                trade.conditions.get("breakout")
            ])

        print("Trade logged successfully")

        elapsed = time.time() - start
        print(f"Elapsed: {elapsed:.4f}s")
