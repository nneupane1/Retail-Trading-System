"""Writes completed backtest trades to CSV with entry, exit, PnL, and setup context."""

import os
import csv
import time

from common.debug import debug_print as print
from config import AppConfig
from simulation.trade import TRADE_LOG_FIELDS, trade_to_log_record


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
            writer.writerow(TRADE_LOG_FIELDS)

        print(f"Logger ready -> {self.filepath}")

    # --------------------------------------------------
    # Log a completed trade
    # --------------------------------------------------

    def log_trade(self, trade):

        print("\nLogging trade...")

        start = time.time()

        with open(self.filepath, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=TRADE_LOG_FIELDS)
            writer.writerow(trade_to_log_record(trade))

        print("Trade logged successfully")

        elapsed = time.time() - start
        print(f"Elapsed: {elapsed:.4f}s")
