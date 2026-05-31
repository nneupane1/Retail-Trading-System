"""Lean bucket-table selector used as a final trade filter and size scaler."""

import json
from pathlib import Path

from config import AppConfig
from entry.edge_buckets import build_signal_bucket


class EdgeSelector:
    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        getter = getattr(self.config, "get", None)
        raw = (
            getter("strategy", "edge_selection", default={})
            if callable(getter)
            else {}
        ) or {}
        self.enabled = bool(raw.get("enabled", False))
        table_path_value = raw.get(
            "table_path",
            "backtest/output/edge_lab/edge_table.json",
        )
        path_getter = getattr(self.config, "path", None)
        if callable(path_getter):
            self.table_path = path_getter(
                "strategy",
                "edge_selection",
                "table_path",
                default=table_path_value,
            )
        else:
            self.table_path = Path(table_path_value)
        self.default_risk_mult = float(raw.get("default_risk_mult", 1.0))
        self.max_risk_mult = float(raw.get("max_risk_mult", 1.5))
        self.min_expected_return = float(raw.get("min_expected_return", 0.0))
        self.edge_table = {}
        self.metadata = {}
        self._load_table()

    @staticmethod
    def _legacy_bucket_aliases(bucket):
        edge_type = str(bucket.get("edge_type") or "")
        bucket_key = tuple(bucket.get("bucket_key") or ())
        if len(bucket_key) != 4:
            return []

        _, bias_bucket, body_bucket, vwap_bucket = bucket_key
        aliases = []
        if edge_type == "impulse_breakout":
            aliases.append(
                f"momentum_long|{bias_bucket}|{body_bucket}|{vwap_bucket}"
            )
        elif edge_type == "momentum_breakout":
            aliases.append(
                f"momentum_long|{bias_bucket}|{body_bucket}|{vwap_bucket}"
            )
        elif edge_type == "pressure_breakout":
            aliases.append(
                f"compression_long|{bias_bucket}|{body_bucket}|{vwap_bucket}"
            )
        elif edge_type == "breakout_pullback":
            aliases.append(
                f"momentum_long|{bias_bucket}|{body_bucket}|{vwap_bucket}"
            )
        elif edge_type == "mean_reversion_vwap":
            aliases.append(
                f"mean_reversion_long|{bias_bucket}|{body_bucket}|{vwap_bucket}"
            )
        elif edge_type == "momentum_breakdown":
            aliases.append(
                f"momentum_short|{bias_bucket}|{body_bucket}|{vwap_bucket}"
            )
        elif edge_type == "compression_expansion_short":
            aliases.append(
                f"compression_short|{bias_bucket}|{body_bucket}|{vwap_bucket}"
            )
        elif edge_type == "mean_reversion_vwap_short":
            aliases.append(
                f"mean_reversion_short|{bias_bucket}|{body_bucket}|{vwap_bucket}"
            )
        return aliases

    def _load_table(self):
        self.edge_table = {}
        self.metadata = {}
        if not self.table_path or not Path(self.table_path).exists():
            return

        with Path(self.table_path).open(encoding="utf-8") as file_handle:
            payload = json.load(file_handle)

        self.metadata = dict(payload.get("metadata") or {})
        buckets = payload.get("buckets") or {}
        self.edge_table = {
            str(key): dict(value or {})
            for key, value in buckets.items()
        }

    def evaluate(self, row, *, bias, side):
        bucket = build_signal_bucket(row, bias=bias, side=side, config=self.config)
        if bucket is None:
            return {
                "edge_selector_enabled": self.enabled,
                "edge_selector_active": False,
                "bucket_valid": False,
                "bucket_reason": "no_edge_type",
                "bucket_risk_mult": 0.0,
                "bucket_expected_return": None,
            }

        record = dict(self.edge_table.get(bucket["bucket_key_text"], {}) or {})
        if not record:
            for alias in self._legacy_bucket_aliases(bucket):
                record = dict(self.edge_table.get(alias, {}) or {})
                if record:
                    break
        expected_return = record.get("expected_return")
        risk_mult = float(record.get("risk_mult", self.default_risk_mult) or self.default_risk_mult)
        valid = bool(record.get("valid", False))
        if expected_return is not None and float(expected_return) < self.min_expected_return:
            valid = False
            record["valid"] = False

        return {
            **bucket,
            "edge_selector_enabled": self.enabled,
            "edge_selector_active": bool(self.enabled and self.edge_table),
            "bucket_valid": valid,
            "bucket_reason": record.get("reason"),
            "bucket_expected_return": (
                float(expected_return) if expected_return is not None else None
            ),
            "bucket_risk_mult": min(self.max_risk_mult, max(0.0, risk_mult)),
            "bucket_signal_count": int(record.get("signal_count", 0) or 0),
            "bucket_selected_horizon": record.get("selected_horizon"),
        }
