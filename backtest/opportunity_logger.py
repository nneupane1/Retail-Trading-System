"""Writes weighted opportunity evaluations to CSV for signal calibration and forensic review."""

import csv
import os

from common.debug import debug_print as print
from config import AppConfig


OPPORTUNITY_LOG_FIELDS = [
    "opportunity_id",
    "timestamp",
    "side",
    "signal_family",
    "bias",
    "regime_score",
    "regime_class",
    "raw_score",
    "score_norm",
    "score_max",
    "momentum_strength",
    "signal_strength",
    "bias_weight",
    "regime_weight",
    "event_bonus",
    "final_strength",
    "entry_risk_multiplier",
    "entry_role",
    "eligible",
    "rejection_reason",
    "structural_floor_passed",
    "breakout_event",
    "price_to_fast_ema_ratio",
    "ema_gap_ratio",
    "vwap_distance_ratio",
    "atr_rising",
    "macd_hist",
    "bias_directional_strength",
    "bias_price_vs_ema_ratio",
    "bias_ema_slope",
    "regime_max_score",
    "regime_normalized_strength",
    "regime_macro_aligned",
    "regime_slope_aligned",
    "regime_trend_aligned",
    "bias_points",
    "trend_points",
    "vwap_points",
    "compression_points",
    "event_points",
    "body_strength_points",
    "close_position_points",
    "wick_points",
    "atr_points",
    "macd_points",
    "bollinger_points",
]


class OpportunityLogger:
    def __init__(self, filepath=None, config=None, reset=True):
        self.config = config or AppConfig.load()
        output_dir = self.config.require("backtest", "output_dir")
        getter = getattr(self.config, "get", None)
        if callable(getter):
            filename = getter(
                "backtest",
                "opportunity_log_filename",
                default="opportunities.csv",
            )
        else:
            filename = "opportunities.csv"
        self.filepath = filepath or os.path.join(output_dir, filename)

        directory = os.path.dirname(self.filepath)
        if directory:
            os.makedirs(directory, exist_ok=True)

        if reset or not os.path.exists(self.filepath):
            with open(self.filepath, "w", newline="", encoding="utf-8") as file_handle:
                writer = csv.writer(file_handle)
                writer.writerow(OPPORTUNITY_LOG_FIELDS)

        print(f"Opportunity logger ready -> {self.filepath}")

    def log_opportunity(self, payload):
        if not payload:
            return

        row = self._build_row(payload)
        with open(self.filepath, "a", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=OPPORTUNITY_LOG_FIELDS)
            writer.writerow(row)

    @staticmethod
    def _build_row(payload):
        score_components = payload.get("score_components") or {}
        bias_snapshot = payload.get("bias_snapshot") or {}
        regime_snapshot = payload.get("regime_snapshot") or {}
        row = {field: payload.get(field) for field in OPPORTUNITY_LOG_FIELDS}

        row.update(
            {
                "bias_directional_strength": payload.get(
                    "bias_directional_strength",
                    bias_snapshot.get("directional_strength"),
                ),
                "bias_price_vs_ema_ratio": payload.get(
                    "bias_price_vs_ema_ratio",
                    bias_snapshot.get("price_vs_ema_ratio"),
                ),
                "bias_ema_slope": payload.get(
                    "bias_ema_slope",
                    bias_snapshot.get("ema_slope"),
                ),
                "regime_max_score": payload.get(
                    "regime_max_score",
                    regime_snapshot.get("max_score"),
                ),
                "regime_normalized_strength": payload.get(
                    "regime_normalized_strength",
                    regime_snapshot.get("normalized_strength"),
                ),
                "regime_macro_aligned": payload.get(
                    "regime_macro_aligned",
                    regime_snapshot.get("macro_aligned"),
                ),
                "regime_slope_aligned": payload.get(
                    "regime_slope_aligned",
                    regime_snapshot.get("slope_aligned"),
                ),
                "regime_trend_aligned": payload.get(
                    "regime_trend_aligned",
                    regime_snapshot.get("trend_aligned"),
                ),
                "bias_points": (score_components.get("bias") or {}).get("points"),
                "trend_points": (score_components.get("trend") or {}).get("points"),
                "vwap_points": (score_components.get("vwap") or {}).get("points"),
                "compression_points": (
                    score_components.get("compression") or {}
                ).get("points"),
                "event_points": (score_components.get("event") or {}).get("points"),
                "body_strength_points": (
                    score_components.get("body_strength") or {}
                ).get("points"),
                "close_position_points": (
                    score_components.get("close_position") or {}
                ).get("points"),
                "wick_points": (score_components.get("wick") or {}).get("points"),
                "atr_points": (score_components.get("atr") or {}).get("points"),
                "macd_points": (score_components.get("macd") or {}).get("points"),
                "bollinger_points": (
                    score_components.get("bollinger") or {}
                ).get("points"),
            }
        )
        return row
