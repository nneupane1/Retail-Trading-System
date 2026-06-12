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
    "bucket_health_mult",
    "bucket_health_source",
    "strategy_health_mult",
    "strategy_health_source",
    "htf_signal_family",
    "htf_score",
    "htf_context_1d",
    "htf_context_1w",
    "htf_entry_reason",
    "htf_stop_reason",
    "htf_trailing_state",
    "htf_decay_reason",
    "htf_candidate_rank",
]

LIVE_ENGINE_CYCLE_FIELDS = [
    "cycle_count",
    "status",
    "cycle_started_at",
    "cycle_completed_at",
    "cycle_duration_seconds",
    "poll_seconds",
    "symbol_count",
    "symbols_with_recent_fetch",
    "total_recent_1m_rows",
    "total_state_1m_rows",
    "latest_recent_1m_timestamp",
    "new_15m_symbol_count",
    "new_15m_symbols",
    "candidates_built",
    "eligible_candidates",
    "allocated_candidates",
    "opened_count",
    "top_symbols",
    "portfolio_open_positions",
    "equity",
]

LIVE_SYMBOL_PIPELINE_FIELDS = [
    "symbol",
    "recent_rows_1m",
    "state_rows_1m",
    "latest_recent_1m_timestamp",
    "latest_15m_timestamp",
    "latest_1h_timestamp",
    "latest_6h_timestamp",
    "latest_12h_timestamp",
    "latest_1d_timestamp",
    "new_15m_candle",
    "candidate_count",
    "candidate_strategies",
    "top_mover",
    "momentum_rank",
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

    def _write_csv(self, filename, fieldnames, rows):
        target = self.output_dir / filename
        with target.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field) for field in fieldnames})

    def _append_csv_row(self, filename, fieldnames, row):
        target = self.output_dir / filename
        exists = target.exists()
        with target.open("a", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
            if not exists:
                writer.writeheader()
            writer.writerow({field: row.get(field) for field in fieldnames})

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

    def write_recent_score_bucket_summary(self, rows):
        target = self.output_dir / "recent_score_bucket_summary.csv"
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

    def write_recent_strategy_layer_summary(self, rows):
        target = self.output_dir / "recent_strategy_layer_summary.csv"
        fieldnames = [
            "strategy_type",
            "count",
            "win_rate",
            "avg_R",
            "total_pnl",
            "risk_multiplier",
        ]
        with target.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field) for field in fieldnames})

    def write_selection_reason_summary(self, rows):
        target = self.output_dir / "selection_reason_summary.csv"
        fieldnames = [
            "selection_reason",
            "count",
            "share_of_decisions",
            "is_cap_pressure",
        ]
        with target.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field) for field in fieldnames})

    def write_recent_selection_reason_summary(self, rows):
        target = self.output_dir / "recent_selection_reason_summary.csv"
        fieldnames = [
            "selection_reason",
            "count",
            "share_of_decisions",
            "is_cap_pressure",
        ]
        with target.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field) for field in fieldnames})

    def write_selection_reason_by_strategy_summary(self, rows):
        target = self.output_dir / "selection_reason_by_strategy_summary.csv"
        fieldnames = [
            "strategy_type",
            "selection_reason",
            "count",
            "share_of_strategy_decisions",
            "is_cap_pressure",
        ]
        with target.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field) for field in fieldnames})

    def write_runtime_policy_summary(self, rows):
        target = self.output_dir / "runtime_policy_summary.csv"
        fieldnames = [
            "strategy_type",
            "enabled",
            "label",
            "fallback_to_short_only",
            "count",
            "avg_R",
            "profit_factor",
            "min_trades",
            "min_avg_R",
            "min_profit_factor",
        ]
        with target.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field) for field in fieldnames})

    def write_engine_heartbeat(self, payload):
        self.write_json("engine_heartbeat.json", payload)

    def append_engine_cycle(self, payload):
        self._append_csv_row("engine_cycle_history.csv", LIVE_ENGINE_CYCLE_FIELDS, payload)

    def write_symbol_pipeline_status(self, rows):
        self._write_csv("symbol_pipeline_status.csv", LIVE_SYMBOL_PIPELINE_FIELDS, rows)

    def write_recent_strategy_bucket_summary(self, rows):
        target = self.output_dir / "recent_strategy_bucket_summary.csv"
        fieldnames = [
            "strategy_type",
            "bucket",
            "count",
            "win_rate",
            "avg_R",
            "total_pnl",
            "risk_multiplier",
            "source",
        ]
        with target.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field) for field in fieldnames})
