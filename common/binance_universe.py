"""Dynamic Binance spot-universe discovery and reporting helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from data.binance_client import BinanceClient


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value, default=0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _upper_list(values) -> list[str]:
    return [
        str(value).upper()
        for value in list(values or [])
        if str(value).strip()
    ]


def get_discovery_settings(config) -> dict:
    getter = getattr(config, "get", None)

    def read(name, default):
        if callable(getter):
            return getter("universe", "discovery", name, default=default)
        return default

    return {
        "enabled": bool(read("enabled", False)),
        "quote_asset": str(read("quote_asset", "USDT") or "USDT").upper(),
        "required_status": str(read("required_status", "TRADING") or "TRADING").upper(),
        "require_spot_permission": bool(read("require_spot_permission", True)),
        "top_n": int(read("top_n", 40) or 40),
        "min_quote_volume_24h": float(read("min_quote_volume_24h", 5_000_000.0) or 5_000_000.0),
        "min_trade_count_24h": int(read("min_trade_count_24h", 5_000) or 5_000),
        "exclude_stable_like_pairs": bool(read("exclude_stable_like_pairs", True)),
        "stable_like_price_min": float(read("stable_like_price_min", 0.95) or 0.95),
        "stable_like_price_max": float(read("stable_like_price_max", 1.05) or 1.05),
        "stable_like_abs_change_pct_max": float(
            read("stable_like_abs_change_pct_max", 0.25) or 0.25
        ),
        "excluded_symbols": _upper_list(read("excluded_symbols", [])),
        "excluded_base_assets": _upper_list(
            read(
                "excluded_base_assets",
                [
                    "BUSD",
                    "FDUSD",
                    "USDC",
                    "TUSD",
                    "USDP",
                    "DAI",
                    "EUR",
                    "TRY",
                    "BRL",
                    "RUB",
                    "UAH",
                    "BIDR",
                    "AUD",
                    "GBP",
                    "JPY",
                ],
            )
        ),
        "excluded_symbol_suffixes": _upper_list(
            read(
                "excluded_symbol_suffixes",
                [
                    "UPUSDT",
                    "DOWNUSDT",
                    "BULLUSDT",
                    "BEARUSDT",
                ],
            )
        ),
        "excluded_base_asset_suffixes": _upper_list(
            read("excluded_base_asset_suffixes", ["UP", "DOWN", "BULL", "BEAR"])
        ),
        "output_prefix": str(read("output_prefix", "binance_discovered_universe") or "binance_discovered_universe"),
        "validation_report_root_name": str(
            read(
                "validation_report_root_name",
                "expanded_universe_allocator_validation_discovered_current",
            )
            or "expanded_universe_allocator_validation_discovered_current"
        ),
    }


def _spot_allowed(symbol_info: dict) -> bool:
    if bool(symbol_info.get("isSpotTradingAllowed")):
        return True

    permissions = symbol_info.get("permissions")
    if isinstance(permissions, list) and "SPOT" in {str(value).upper() for value in permissions}:
        return True

    permission_sets = symbol_info.get("permissionSets")
    if isinstance(permission_sets, list):
        for permission_set in permission_sets:
            values = {str(value).upper() for value in list(permission_set or [])}
            if "SPOT" in values:
                return True

    return False


def discover_binance_candidate_universe(
    config,
    *,
    client: BinanceClient | None = None,
    top_n: int | None = None,
) -> dict:
    settings = get_discovery_settings(config)
    active_top_n = int(top_n or settings["top_n"])
    client = client or BinanceClient(config=config)

    exchange_info = client.get_exchange_info(verbose=False) or {}
    ticker_rows = client.get_ticker_24hr(verbose=False) or []
    ticker_map = {
        str(item.get("symbol", "")).upper(): dict(item)
        for item in list(ticker_rows or [])
        if str(item.get("symbol", "")).strip()
    }

    all_rows = []
    prefiltered_rows = []

    for symbol_info in list(exchange_info.get("symbols", []) or []):
        symbol = str(symbol_info.get("symbol", "")).upper()
        if not symbol:
            continue

        base_asset = str(symbol_info.get("baseAsset", "")).upper()
        quote_asset = str(symbol_info.get("quoteAsset", "")).upper()
        status = str(symbol_info.get("status", "")).upper()
        ticker = ticker_map.get(symbol, {})
        quote_volume_24h = _safe_float(ticker.get("quoteVolume"), 0.0)
        trade_count_24h = _safe_int(ticker.get("count"), 0)
        spot_allowed = _spot_allowed(symbol_info)
        last_price_24h = _safe_float(ticker.get("lastPrice"), 0.0)
        price_change_pct_24h = _safe_float(ticker.get("priceChangePercent"), 0.0)

        reasons = []
        if symbol in set(settings["excluded_symbols"]):
            reasons.append("excluded_symbol")
        if any(symbol.endswith(suffix) for suffix in settings["excluded_symbol_suffixes"]):
            reasons.append("excluded_symbol_suffix")
        if base_asset in set(settings["excluded_base_assets"]):
            reasons.append("excluded_base_asset")
        if any(base_asset.endswith(suffix) for suffix in settings["excluded_base_asset_suffixes"]):
            reasons.append("excluded_base_asset_suffix")
        if quote_asset != settings["quote_asset"]:
            reasons.append("quote_asset_mismatch")
        if status != settings["required_status"]:
            reasons.append("status_not_trading")
        if settings["require_spot_permission"] and not spot_allowed:
            reasons.append("spot_not_allowed")
        if not ticker:
            reasons.append("missing_24h_ticker")
        if quote_volume_24h < settings["min_quote_volume_24h"]:
            reasons.append("low_24h_quote_volume")
        if trade_count_24h < settings["min_trade_count_24h"]:
            reasons.append("low_24h_trade_count")
        if (
            settings["exclude_stable_like_pairs"]
            and settings["stable_like_price_min"] <= last_price_24h <= settings["stable_like_price_max"]
            and abs(price_change_pct_24h) <= settings["stable_like_abs_change_pct_max"]
        ):
            reasons.append("stable_like_pair")

        row = {
            "symbol": symbol,
            "base_asset": base_asset,
            "quote_asset": quote_asset,
            "status": status,
            "spot_allowed": bool(spot_allowed),
            "quote_volume_24h": quote_volume_24h,
            "trade_count_24h": trade_count_24h,
            "weighted_avg_price_24h": _safe_float(ticker.get("weightedAvgPrice"), 0.0),
            "last_price_24h": last_price_24h,
            "price_change_pct_24h": price_change_pct_24h,
            "permissions": ",".join(str(value) for value in list(symbol_info.get("permissions") or [])),
            "reject_reason": "|".join(reasons),
            "passed_prefilters": not reasons,
            "liquidity_rank": None,
            "selected_for_candidate_pool": False,
        }
        all_rows.append(row)
        if not reasons:
            prefiltered_rows.append(row)

    prefiltered_rows.sort(
        key=lambda item: (
            float(item["quote_volume_24h"]),
            int(item["trade_count_24h"]),
            str(item["symbol"]),
        ),
        reverse=True,
    )

    candidate_symbols = []
    for index, row in enumerate(prefiltered_rows, start=1):
        row["liquidity_rank"] = index
        if index <= active_top_n:
            row["selected_for_candidate_pool"] = True
            candidate_symbols.append(row["symbol"])
        else:
            row["reject_reason"] = "outside_top_n_liquidity_rank"

    selected_rows = [row for row in prefiltered_rows if row["selected_for_candidate_pool"]]
    rejected_rows = [row for row in all_rows if not row["selected_for_candidate_pool"]]

    return {
        "generated_at": _utc_now_iso(),
        "settings": settings,
        "all_rows": all_rows,
        "selected_rows": selected_rows,
        "rejected_rows": rejected_rows,
        "candidate_symbols": candidate_symbols,
        "summary": {
            "generated_at": _utc_now_iso(),
            "candidate_symbol_count": len(candidate_symbols),
            "prefilter_pass_count": len(prefiltered_rows),
            "total_exchange_symbol_count": len(all_rows),
            "rejected_count": len(rejected_rows),
            "top_n": active_top_n,
            "quote_asset": settings["quote_asset"],
            "required_status": settings["required_status"],
            "min_quote_volume_24h": settings["min_quote_volume_24h"],
            "min_trade_count_24h": settings["min_trade_count_24h"],
            "candidate_symbols": candidate_symbols,
        },
    }


def write_discovery_reports(report_root: Path, payload: dict) -> dict:
    report_root.mkdir(parents=True, exist_ok=True)
    prefix = payload.get("settings", {}).get("output_prefix", "binance_discovered_universe")
    all_path = report_root / f"{prefix}.csv"
    selected_path = report_root / f"{prefix}_selected.csv"
    rejected_path = report_root / f"{prefix}_rejected.csv"
    summary_path = report_root / f"{prefix}_summary.json"

    pd.DataFrame(payload.get("all_rows", [])).to_csv(all_path, index=False)
    pd.DataFrame(payload.get("selected_rows", [])).to_csv(selected_path, index=False)
    pd.DataFrame(payload.get("rejected_rows", [])).to_csv(rejected_path, index=False)

    serializable = {
        "generated_at": payload.get("generated_at"),
        "settings": payload.get("settings", {}),
        "summary": payload.get("summary", {}),
        "artifacts": {
            "all_rows_csv": str(all_path),
            "selected_rows_csv": str(selected_path),
            "rejected_rows_csv": str(rejected_path),
            "summary_json": str(summary_path),
        },
    }
    summary_path.write_text(json.dumps(serializable, indent=2, default=str), encoding="utf-8")
    return serializable
