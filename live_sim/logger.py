"""Writes completed live-simulation trades and scan telemetry."""

import os
import csv
import time
import json
from pathlib import Path

from common.debug import debug_print as print
from config import AppConfig
from simulation.trade import TRADE_LOG_FIELDS, trade_to_log_record


LIVE_SIGNAL_LOG_FIELDS = [
    "timestamp",
    "symbol",
    "side",
    "edge_type",
    "bias",
    "body_bucket",
    "vwap_bucket",
    "bucket_key",
    "is_top_mover",
    "momentum_rank",
    "score",
    "selection_score",
    "score_bucket",
    "strategy_type",
    "risk_group",
    "moonshot_score",
    "range_expansion_factor",
    "threshold",
    "selected",
    "selection_reason",
    "bucket_valid",
    "bucket_expected_return",
    "bucket_risk_mult",
]


class _CsvLoggerBase:
    def __init__(self, filepath, fieldnames, reset=False):
        self.filepath = filepath
        self.fieldnames = list(fieldnames)

        directory = os.path.dirname(self.filepath)
        if directory:
            os.makedirs(directory, exist_ok=True)

        if reset or not os.path.exists(self.filepath):
            with open(self.filepath, "w", newline="", encoding="utf-8") as file_handle:
                writer = csv.writer(file_handle)
                writer.writerow(self.fieldnames)

    def _write_row(self, payload):
        with open(self.filepath, "a", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=self.fieldnames)
            writer.writerow(payload)


class LiveTradeLogger:
    """
    Logs trades from live simulation into CSV.

    Similar to backtest logger but stored separately.
    """

    def __init__(self, filepath=None, config=None):

        print("\nInitializing LIVE Trade Logger...")

        self.config = config or AppConfig.load()
        if filepath is not None:
            self.filepath = filepath
        else:
            output_dir = self.config.require("live_sim", "output_dir")
            self.filepath = os.path.join(output_dir, "trades.csv")

        self._base = _CsvLoggerBase(self.filepath, TRADE_LOG_FIELDS)

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


class LiveSignalLogger:
    """Logs scored live candidates before portfolio selection."""

    def __init__(self, filepath=None, config=None, reset=False):
        self.config = config or AppConfig.load()
        if filepath is not None:
            self.filepath = filepath
        else:
            output_dir = self.config.require("live_sim", "output_dir")
            self.filepath = os.path.join(output_dir, "signals.csv")
        self._base = _CsvLoggerBase(self.filepath, LIVE_SIGNAL_LOG_FIELDS, reset=reset)

    def log_signal(self, payload):
        if not payload:
            return

        row = {field: payload.get(field) for field in LIVE_SIGNAL_LOG_FIELDS}
        self._base._write_row(row)


class LivePortfolioStateLogger:
    """Writes live paper-portfolio state artifacts for diagnostics."""

    def __init__(self, output_dir=None, config=None):
        self.config = config or AppConfig.load()
        configured_dir = output_dir or self.config.require("live_sim", "output_dir")
        self.output_dir = Path(configured_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_json(self, filename, payload):
        target = self.output_dir / filename
        with target.open("w", encoding="utf-8") as file_handle:
            json.dump(payload, file_handle, indent=2, default=str)

    def write_score_bucket_summary(self, rows):
        target = self.output_dir / "score_bucket_summary.csv"
        fieldnames = [
            "bucket",
            "count",
            "win_rate",
            "avg_R",
            "total_pnl",
        ]
        with target.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field) for field in fieldnames})

    def write_daily_summary(self, rows):
        target = self.output_dir / "daily_summary.csv"
        fieldnames = [
            "date",
            "equity_start",
            "equity_end",
            "realized_pnl",
            "realized_return_fraction",
            "entries_taken",
            "closed_trades",
            "threshold",
        ]
        with target.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field) for field in fieldnames})

    def write_strategy_layer_summary(self, rows):
        target = self.output_dir / "strategy_layer_summary.csv"
        fieldnames = [
            "strategy_type",
            "count",
            "win_rate",
            "avg_R",
            "total_pnl",
        ]
        with target.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field) for field in fieldnames})
