"""Writes completed live-simulation trades to a dedicated CSV output."""

import os
import csv
import time

from common.debug import debug_print as print
from config import AppConfig
from simulation.trade import TRADE_LOG_FIELDS, trade_to_log_record


class LiveTradeLogger:
    """
    Logs trades from live simulation into CSV.

    Similar to backtest logger but stored separately.
    """

    def __init__(self, filepath=None, config=None):

        print("\nInitializing LIVE Trade Logger...")

        self.config = config or AppConfig.load()
        output_dir = self.config.require("live_sim", "output_dir")
        self.filepath = filepath or os.path.join(output_dir, "trades.csv")

        # ensure folder exists
        directory = os.path.dirname(self.filepath)
        if directory:
            os.makedirs(directory, exist_ok=True)

        # create file with header (only once)
        if not os.path.exists(self.filepath):
            with open(self.filepath, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(TRADE_LOG_FIELDS)

        print(f"Live logger ready -> {self.filepath}")

    # ------------------------------------------
    # Log completed trade
    # ------------------------------------------

    def log_trade(self, trade):

        print("\nLogging LIVE trade...")

        start = time.time()

        with open(self.filepath, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=TRADE_LOG_FIELDS)
            writer.writerow(trade_to_log_record(trade))

        print("LIVE trade logged")

        print(f"Elapsed: {time.time() - start:.4f}s")
