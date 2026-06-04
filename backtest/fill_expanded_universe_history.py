"""Checkpoint-safe downloader for missing local history in expanded universes."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from common.binance_universe import (
    discover_binance_candidate_universe,
    get_discovery_settings,
    write_discovery_reports,
)
from common.universe import get_named_universe
from config import AppConfig
from data.downloader import MarketDataDownloader


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Fill missing local 1m history for an expanded Binance universe using "
            "checkpoint-safe per-symbol downloads."
        )
    )
    parser.add_argument(
        "--validation-report-root",
        help=(
            "Optional expanded-universe validation report root. If omitted, the "
            "latest matching folder under backtest/output is used."
        ),
    )
    parser.add_argument(
        "--report-root",
        help=(
            "Optional output folder for fill progress. Defaults to "
            "backtest/output/expanded_universe_history_fill_active."
        ),
    )
    parser.add_argument(
        "--universe-name",
        default="expanded_liquid_28",
        help="Named universe from config.universe.symbol_sets to source symbols from.",
    )
    parser.add_argument(
        "--symbols",
        help="Optional comma-separated symbol override.",
    )
    parser.add_argument(
        "--start-date",
        dest="start_date",
        help="Inclusive UTC start date override. Defaults to config.history.start_date.",
    )
    parser.add_argument(
        "--end-date",
        dest="end_date",
        help="Inclusive UTC end date override. Defaults to config.history.end_date.",
    )
    parser.add_argument(
        "--base-path",
        dest="base_path",
        help="Storage root override. Defaults to config.storage.base_path.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional cap on the number of target symbols for a smoke run.",
    )
    parser.add_argument(
        "--use-binance-discovery",
        action="store_true",
        help="Source candidate symbols from live Binance discovery instead of a static named universe.",
    )
    return parser


def _default_report_root(base_output: Path) -> Path:
    return base_output / "expanded_universe_history_fill_active"


def _find_latest_validation_root(base_output: Path) -> Path | None:
    candidates = []
    for candidate in base_output.glob("expanded_universe_allocator_validation*"):
        rejected_csv = candidate / "expanded_universe_rejected_symbols.csv"
        if candidate.is_dir() and rejected_csv.exists():
            candidates.append(candidate)
    if not candidates:
        return None
    candidates.sort(key=lambda path: path.name, reverse=True)
    return candidates[0]


def _progress_path(report_root: Path) -> Path:
    return report_root / "history_fill_progress.json"


def _targets_path(report_root: Path) -> Path:
    return report_root / "history_fill_targets.csv"


def _status_path(report_root: Path) -> Path:
    return report_root / "history_fill_status.csv"


def _summary_path(report_root: Path) -> Path:
    return report_root / "history_fill_summary.json"


def _load_progress(report_root: Path) -> dict:
    path = _progress_path(report_root)
    if not path.exists():
        return {
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            "symbols": {},
        }
    try:
        with path.open(encoding="utf-8") as file_handle:
            payload = json.load(file_handle)
    except Exception:
        return {
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            "symbols": {},
        }
    payload.setdefault("symbols", {})
    payload.setdefault("created_at", _utc_now_iso())
    payload["updated_at"] = _utc_now_iso()
    return payload


def _save_progress(report_root: Path, payload: dict) -> None:
    report_root.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = _utc_now_iso()
    with _progress_path(report_root).open("w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2, default=str)


def _parse_symbol_override(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    return sorted(
        {
            str(symbol).upper()
            for symbol in raw_value.split(",")
            if str(symbol).strip()
        }
    )


def _load_rejected_symbols(validation_root: Path) -> pd.DataFrame:
    rejected_path = validation_root / "expanded_universe_rejected_symbols.csv"
    if not rejected_path.exists():
        raise FileNotFoundError(f"Rejected-symbol report not found: {rejected_path}")
    frame = pd.read_csv(rejected_path)
    if "symbol" not in frame.columns:
        raise ValueError(f"Rejected-symbol report missing symbol column: {rejected_path}")
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    if "reject_reason" in frame.columns:
        frame["reject_reason"] = frame["reject_reason"].fillna("").astype(str)
    else:
        frame["reject_reason"] = ""
    return frame


def _build_target_rows(
    *,
    base_config: AppConfig,
    validation_root: Path | None,
    universe_name: str,
    symbol_override: list[str],
    report_root: Path | None = None,
    use_binance_discovery: bool = False,
) -> list[dict]:
    current_symbols = {
        str(symbol).upper()
        for symbol in get_named_universe(base_config, "current_9")
    }

    if symbol_override:
        return [
            {
                "symbol": symbol,
                "source": "cli_override",
                "target_reason": "explicit_symbol_override",
                "in_current_9": symbol in current_symbols,
            }
            for symbol in symbol_override
        ]

    if validation_root is not None:
        rejected = _load_rejected_symbols(validation_root)
        missing_history = rejected.loc[
            rejected["reject_reason"].eq("missing_local_history"),
            "symbol",
        ].astype(str).str.upper().tolist()
        if missing_history:
            return [
                {
                    "symbol": symbol,
                    "source": str(validation_root),
                    "target_reason": "missing_local_history",
                    "in_current_9": symbol in current_symbols,
                }
                for symbol in missing_history
            ]

    discovery_settings = get_discovery_settings(base_config)
    should_use_discovery = bool(use_binance_discovery or discovery_settings["enabled"])
    if should_use_discovery:
        payload = discover_binance_candidate_universe(base_config)
        if report_root is not None:
            write_discovery_reports(report_root, payload)
        candidate_symbols = [
            str(symbol).upper()
            for symbol in payload.get("candidate_symbols", [])
        ]
        source_label = "binance_discovery"
    else:
        candidate_symbols = [
            str(symbol).upper()
            for symbol in get_named_universe(base_config, universe_name)
        ]
        source_label = f"universe:{universe_name}"

    if not candidate_symbols:
        raise ValueError("No candidate symbols resolved for history fill.")

    return [
        {
            "symbol": symbol,
            "source": source_label,
            "target_reason": "candidate_universe_fill",
            "in_current_9": symbol in current_symbols,
        }
        for symbol in candidate_symbols
        if symbol not in current_symbols
    ]


def _write_target_report(report_root: Path, target_rows: list[dict]) -> None:
    report_root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(target_rows).to_csv(_targets_path(report_root), index=False)


def _write_status_reports(
    *,
    report_root: Path,
    progress: dict,
    target_rows: list[dict],
    context: dict,
) -> dict:
    report_root.mkdir(parents=True, exist_ok=True)
    target_index = {row["symbol"]: dict(row) for row in target_rows}
    rows = []
    for symbol in sorted(target_index):
        row = dict(target_index[symbol])
        row.update(progress["symbols"].get(symbol, {}))
        row.setdefault("symbol", symbol)
        row.setdefault("status", "pending")
        rows.append(row)

    status_df = pd.DataFrame(rows)
    if not status_df.empty:
        status_df = status_df.sort_values(["status", "symbol"]).reset_index(drop=True)
    status_df.to_csv(_status_path(report_root), index=False)

    counts = (
        status_df["status"].value_counts().to_dict()
        if not status_df.empty and "status" in status_df.columns
        else {}
    )
    completed = [
        row["symbol"]
        for row in rows
        if str(row.get("status", "")).lower() == "completed"
    ]
    pending = [
        row["symbol"]
        for row in rows
        if str(row.get("status", "")).lower() not in {"completed"}
    ]
    summary = {
        "report_root": str(report_root),
        "validation_report_root": context.get("validation_report_root"),
        "universe_name": context.get("universe_name"),
        "start_date": context.get("start_date"),
        "end_date": context.get("end_date"),
        "base_path": context.get("base_path"),
        "target_symbol_count": int(len(target_rows)),
        "status_counts": {str(key): int(value) for key, value in counts.items()},
        "completed_symbols": completed,
        "pending_symbols": pending,
        "resume_command": "python -m backtest.fill_expanded_universe_history",
        "targets_report": str(_targets_path(report_root)),
        "status_report": str(_status_path(report_root)),
        "progress_file": str(_progress_path(report_root)),
    }
    with _summary_path(report_root).open("w", encoding="utf-8") as file_handle:
        json.dump(summary, file_handle, indent=2, default=str)
    return summary


def main():
    args = _build_parser().parse_args()
    base_config = AppConfig.load()
    base_output = Path(base_config.require("backtest", "output_dir"))
    report_root = Path(args.report_root) if args.report_root else _default_report_root(base_output)
    validation_root = (
        Path(args.validation_report_root)
        if args.validation_report_root
        else _find_latest_validation_root(base_output)
    )

    start_date = args.start_date or str(base_config.require("history", "start_date"))
    end_date = args.end_date or str(base_config.require("history", "end_date"))
    base_path = args.base_path or str(base_config.require("storage", "base_path"))
    interval = str(base_config.require("binance", "default_interval"))

    symbol_override = _parse_symbol_override(args.symbols)
    target_rows = _build_target_rows(
        base_config=base_config,
        validation_root=validation_root,
        universe_name=args.universe_name,
        symbol_override=symbol_override,
        report_root=report_root,
        use_binance_discovery=bool(args.use_binance_discovery),
    )
    if args.limit and args.limit > 0:
        target_rows = target_rows[: args.limit]
    if not target_rows:
        raise RuntimeError("No target symbols were resolved for history filling.")

    progress = _load_progress(report_root)
    context = {
        "validation_report_root": str(validation_root) if validation_root is not None else None,
        "universe_name": args.universe_name,
        "start_date": start_date,
        "end_date": end_date,
        "base_path": base_path,
    }
    _write_target_report(report_root, target_rows)
    _write_status_reports(report_root=report_root, progress=progress, target_rows=target_rows, context=context)

    downloader = MarketDataDownloader(config=base_config)
    target_symbols = [row["symbol"] for row in target_rows]

    for position, symbol in enumerate(target_symbols, start=1):
        entry = progress["symbols"].get(symbol, {})
        if str(entry.get("status", "")).lower() == "completed":
            continue

        paths = downloader._history_paths(  # pylint: disable=protected-access
            symbol=symbol,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
            base_path=base_path,
        )
        started_at = _utc_now_iso()
        progress["symbols"][symbol] = {
            "symbol": symbol,
            "status": "in_progress",
            "position": position,
            "started_at": entry.get("started_at", started_at),
            "last_attempt_started_at": started_at,
            "target_reason": next(
                (row["target_reason"] for row in target_rows if row["symbol"] == symbol),
                "",
            ),
            "final_csv_path": str(paths["final"]),
            "download_checkpoint_path": str(paths["checkpoint"]),
        }
        _save_progress(report_root, progress)
        _write_status_reports(
            report_root=report_root,
            progress=progress,
            target_rows=target_rows,
            context=context,
        )

        started = time.time()
        try:
            df = downloader.fetch_full_history(
                symbol=symbol,
                interval=interval,
                start_date=start_date,
                end_date=end_date,
                base_path=base_path,
            )
        except KeyboardInterrupt:
            progress["symbols"][symbol]["status"] = "interrupted"
            progress["symbols"][symbol]["interrupted_at"] = _utc_now_iso()
            progress["symbols"][symbol]["elapsed_seconds_last_attempt"] = round(time.time() - started, 3)
            _save_progress(report_root, progress)
            _write_status_reports(
                report_root=report_root,
                progress=progress,
                target_rows=target_rows,
                context=context,
            )
            raise
        except Exception as exc:
            progress["symbols"][symbol]["status"] = "failed"
            progress["symbols"][symbol]["failed_at"] = _utc_now_iso()
            progress["symbols"][symbol]["elapsed_seconds_last_attempt"] = round(time.time() - started, 3)
            progress["symbols"][symbol]["error"] = str(exc)
            _save_progress(report_root, progress)
            _write_status_reports(
                report_root=report_root,
                progress=progress,
                target_rows=target_rows,
                context=context,
            )
            continue

        progress["symbols"][symbol]["status"] = "completed"
        progress["symbols"][symbol]["completed_at"] = _utc_now_iso()
        progress["symbols"][symbol]["elapsed_seconds_last_attempt"] = round(time.time() - started, 3)
        progress["symbols"][symbol]["rows_downloaded"] = int(len(df))
        progress["symbols"][symbol]["final_csv_exists"] = bool(paths["final"].exists())
        _save_progress(report_root, progress)
        _write_status_reports(
            report_root=report_root,
            progress=progress,
            target_rows=target_rows,
            context=context,
        )

    summary = _write_status_reports(
        report_root=report_root,
        progress=progress,
        target_rows=target_rows,
        context=context,
    )
    print("\nExpanded-universe history fill finished.")
    print(f"Report root: {report_root}")
    print(f"Targets: {summary['target_symbol_count']}")
    print(f"Status counts: {summary['status_counts']}")


if __name__ == "__main__":
    main()
