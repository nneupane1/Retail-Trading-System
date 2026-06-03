"""Forward-return study for 12H moonshot candidates across the full universe."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.portfolio_runner import (
    _build_strategy_timeframes,
    _discover_portfolio_symbols,
    _load_full_history,
)
from config import AppConfig
from entry.htf_moonshot import HTFMoonshotEngine, build_htf_12h_snapshots
from entry.opportunity_ranking import score_bucket_label


HORIZONS = (1, 3, 6, 12)


def _safe_float(value, default=0.0):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return float(default)
    if pd.isna(numeric):
        return float(default)
    return numeric


def _forward_metrics(df_12h, signal_index: int, side: str, stop_price: float) -> dict:
    metrics = {}
    if signal_index + 1 >= len(df_12h):
        for horizon in HORIZONS:
            metrics[f"fwd_return_{horizon}"] = np.nan
            metrics[f"fwd_R_{horizon}"] = np.nan
        return metrics

    entry_price = _safe_float(df_12h.iloc[signal_index + 1]["open"], default=np.nan)
    if not np.isfinite(entry_price):
        for horizon in HORIZONS:
            metrics[f"fwd_return_{horizon}"] = np.nan
            metrics[f"fwd_R_{horizon}"] = np.nan
        return metrics

    risk_per_unit = abs(entry_price - stop_price)
    if risk_per_unit <= 0.0:
        risk_per_unit = np.nan

    for horizon in HORIZONS:
        future_index = signal_index + horizon
        if future_index >= len(df_12h):
            metrics[f"fwd_return_{horizon}"] = np.nan
            metrics[f"fwd_R_{horizon}"] = np.nan
            continue

        future_close = _safe_float(df_12h.iloc[future_index]["close"], default=np.nan)
        if not np.isfinite(future_close):
            metrics[f"fwd_return_{horizon}"] = np.nan
            metrics[f"fwd_R_{horizon}"] = np.nan
            continue

        if side == "short":
            pnl_per_unit = entry_price - future_close
            return_fraction = pnl_per_unit / entry_price
        else:
            pnl_per_unit = future_close - entry_price
            return_fraction = pnl_per_unit / entry_price

        metrics[f"fwd_return_{horizon}"] = return_fraction
        metrics[f"fwd_R_{horizon}"] = pnl_per_unit / risk_per_unit if np.isfinite(risk_per_unit) else np.nan

    return metrics


def _load_htf_only_signal_reasons(base_output: Path) -> pd.DataFrame:
    signals_path = (
        base_output
        / "htf_12h_validation_20260601"
        / "scenario_htf_only"
        / "signals.csv"
    )
    if not signals_path.exists():
        return pd.DataFrame()

    signals = pd.read_csv(signals_path, on_bad_lines="skip", engine="python")
    if signals.empty or "strategy_type" not in signals.columns:
        return pd.DataFrame()

    signals = signals.loc[signals["strategy_type"].astype(str) == "htf_12h_moonshot"].copy()
    if signals.empty:
        return pd.DataFrame()

    signals["timestamp"] = pd.to_datetime(signals["timestamp"], errors="coerce")
    signals = signals.dropna(subset=["timestamp"])
    signals["side"] = signals["side"].fillna("long").astype(str)
    signals["symbol"] = signals["symbol"].astype(str)
    signals["selection_reason"] = signals["selection_reason"].fillna("unknown").astype(str)
    if "htf_signal_family" not in signals.columns:
        signals["htf_signal_family"] = "unknown"
    else:
        signals["htf_signal_family"] = signals["htf_signal_family"].fillna("unknown").astype(str)

    return signals[
        [
            "timestamp",
            "symbol",
            "side",
            "selection_reason",
            "htf_signal_family",
            "htf_score",
            "htf_candidate_rank",
        ]
    ].drop_duplicates(subset=["timestamp", "symbol", "side"], keep="last")


def _gate_label(row) -> str:
    if not bool(row["passed_12h_structure"]):
        return "structure_gate"
    if not bool(row["passed_1d_context"]):
        return "context_1d_gate"
    if not bool(row["passed_1w_context"]):
        return "context_1w_gate"
    if not bool(row["passed_stretch_filter"]):
        return "stretch_gate"
    if not bool(row["passed_score"]):
        return "score_gate"
    if not bool(row["passed_expansion"]):
        return "expansion_gate"
    return "passed_pre_open"


def _build_candidate_rows(config: AppConfig) -> pd.DataFrame:
    symbols = _discover_portfolio_symbols(config)
    interval = config.require("binance", "default_interval")
    htf_engine = HTFMoonshotEngine(config=config)
    rows = []

    for symbol in symbols:
        df_1m, _ = _load_full_history(symbol, interval, config)
        df_15m, _, df_12h, df_1d, df_1w = _build_strategy_timeframes(df_1m, config=config)
        aligned = build_htf_12h_snapshots(df_15m.index, df_12h, df_1d, df_1w, config=config)
        new_candles = aligned.loc[aligned["htf_12h_new_candle"] == True].copy()  # noqa: E712
        if new_candles.empty:
            continue

        for timestamp, snapshot in new_candles.iterrows():
            if timestamp not in df_12h.index:
                continue
            signal_idx = int(df_12h.index.get_loc(timestamp))

            for side in ("long", "short"):
                signal_family = str(snapshot.get(f"signal_family_{side}", "") or "")
                raw_score = _safe_float(snapshot.get(f"htf_score_{side}"), default=0.0)
                score_norm = raw_score / htf_engine.MAX_SCORE
                stop_price = _safe_float(snapshot.get(f"htf_stop_{side}"), default=np.nan)
                if not np.isfinite(stop_price):
                    continue

                record = {
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "year": int(timestamp.year),
                    "side": side,
                    "signal_family": signal_family if signal_family else "none",
                    "raw_score": raw_score,
                    "score_norm": score_norm,
                    "score_bucket": score_bucket_label(score_norm),
                    "passed_12h_structure": bool(snapshot.get(f"htf_pass_structure_{side}", False)),
                    "passed_1d_context": bool(snapshot.get(f"htf_pass_1d_context_{side}", False)),
                    "passed_1w_context": bool(snapshot.get(f"htf_pass_1w_context_{side}", False)),
                    "passed_stretch_filter": bool(snapshot.get(f"htf_pass_stretch_{side}", False)),
                    "passed_score": bool(snapshot.get(f"htf_pass_score_{side}", False)),
                    "passed_expansion": bool(snapshot.get(f"htf_pass_expansion_{side}", False)),
                    "context_1d": str(snapshot.get("htf_context_1d", "neutral") or "neutral"),
                    "context_1w": str(snapshot.get("htf_context_1w", "neutral") or "neutral"),
                    "range_expansion_12h": _safe_float(snapshot.get("htf_range_expansion_12h"), default=np.nan),
                    "vwap_distance_ratio_12h": _safe_float(snapshot.get("htf_vwap_distance_ratio_12h"), default=np.nan),
                    "ema_gap_ratio_12h": _safe_float(snapshot.get("htf_ema_gap_ratio_12h"), default=np.nan),
                    "body_strength_12h": _safe_float(snapshot.get("htf_body_strength_12h"), default=np.nan),
                    "close_position_12h": _safe_float(snapshot.get("htf_close_position_12h"), default=np.nan),
                }
                record["gate_label"] = _gate_label(record)
                record["passed_pre_open"] = record["gate_label"] == "passed_pre_open"
                record.update(_forward_metrics(df_12h, signal_idx, side, stop_price))
                rows.append(record)

    return pd.DataFrame(rows)


def _summary_table(df: pd.DataFrame, group_columns: list[str], prefix: str) -> pd.DataFrame:
    rows = []
    if df.empty:
        return pd.DataFrame()

    for group_key, group in df.groupby(group_columns, dropna=False):
        if not isinstance(group_key, tuple):
            group_key = (group_key,)
        row = dict(zip(group_columns, group_key))
        row["count"] = int(len(group))
        for horizon in HORIZONS:
            returns = pd.to_numeric(group[f"fwd_return_{horizon}"], errors="coerce").dropna()
            r_vals = pd.to_numeric(group[f"fwd_R_{horizon}"], errors="coerce").dropna()
            row[f"{prefix}_avg_return_{horizon}"] = float(returns.mean()) if not returns.empty else np.nan
            row[f"{prefix}_median_return_{horizon}"] = float(returns.median()) if not returns.empty else np.nan
            row[f"{prefix}_win_rate_{horizon}"] = float((returns > 0).mean()) if not returns.empty else np.nan
            row[f"{prefix}_avg_R_{horizon}"] = float(r_vals.mean()) if not r_vals.empty else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    config = AppConfig.load()
    config.data.setdefault("app", {})["debug"] = False
    output_root = Path(config.require("backtest", "output_dir")) / "htf_12h_forward_return_20260602"
    output_root.mkdir(parents=True, exist_ok=True)

    candidates = _build_candidate_rows(config)
    candidates.to_csv(output_root / "htf_forward_candidates.csv", index=False)

    htf_only_signals = _load_htf_only_signal_reasons(Path(config.require("backtest", "output_dir")))
    if not htf_only_signals.empty:
        candidates = candidates.merge(
            htf_only_signals,
            on=["timestamp", "symbol", "side"],
            how="left",
            suffixes=("", "_htf_only"),
        )
    else:
        candidates["selection_reason"] = np.nan

    candidates["selection_reason"] = candidates["selection_reason"].fillna("not_candidate")

    overall = _summary_table(candidates, ["passed_pre_open"], prefix="fwd")
    by_gate = _summary_table(candidates, ["gate_label"], prefix="fwd")
    by_family = _summary_table(candidates.loc[candidates["signal_family"] != "none"], ["signal_family"], prefix="fwd")
    by_score_bucket = _summary_table(candidates, ["score_bucket"], prefix="fwd")
    by_pass_and_bucket = _summary_table(candidates, ["passed_pre_open", "score_bucket"], prefix="fwd")
    by_selection_reason = _summary_table(
        candidates.loc[candidates["selection_reason"] != "not_candidate"],
        ["selection_reason"],
        prefix="fwd",
    )
    by_selection_reason_and_family = _summary_table(
        candidates.loc[candidates["selection_reason"] != "not_candidate"],
        ["selection_reason", "signal_family"],
        prefix="fwd",
    )
    recent = candidates.loc[candidates["timestamp"] >= pd.Timestamp("2025-01-01")].copy()
    recent_by_gate = _summary_table(recent, ["gate_label"], prefix="recent")
    recent_by_family = _summary_table(recent.loc[recent["signal_family"] != "none"], ["signal_family"], prefix="recent")

    overall.to_csv(output_root / "forward_overall.csv", index=False)
    by_gate.to_csv(output_root / "forward_by_gate.csv", index=False)
    by_family.to_csv(output_root / "forward_by_signal_family.csv", index=False)
    by_score_bucket.to_csv(output_root / "forward_by_score_bucket.csv", index=False)
    by_pass_and_bucket.to_csv(output_root / "forward_by_pass_and_score_bucket.csv", index=False)
    by_selection_reason.to_csv(output_root / "forward_by_selection_reason.csv", index=False)
    by_selection_reason_and_family.to_csv(output_root / "forward_by_selection_reason_and_family.csv", index=False)
    recent_by_gate.to_csv(output_root / "recent_forward_by_gate.csv", index=False)
    recent_by_family.to_csv(output_root / "recent_forward_by_signal_family.csv", index=False)

    summary = {
        "output_root": str(output_root),
        "candidate_count": int(len(candidates)),
        "passed_pre_open_count": int(candidates["passed_pre_open"].sum()),
        "gate_counts": candidates["gate_label"].value_counts().to_dict(),
        "selection_reason_counts": candidates["selection_reason"].value_counts().to_dict(),
    }
    with (output_root / "summary.json").open("w", encoding="utf-8") as file_handle:
        json.dump(summary, file_handle, indent=2, default=str)
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
