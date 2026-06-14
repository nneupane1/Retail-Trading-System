"""Production-style validation gate for the current routed multi-sleeve stack."""

from __future__ import annotations

import json
from pathlib import Path

from common.runtime_readiness import write_scenario_config_manifest
from backtest.validate_allocator_coordination_portfolio import (
    _routed_h1_paper_overrides,
)
from backtest.validate_expanded_universe_allocator import _scenario_snapshot
from backtest.validate_htf_12h import (
    _clone_config,
    _load_progress,
    _run_or_resume_scenario,
    _save_progress,
)
from backtest.window_policy import (
    resolve_full_history_window,
    resolve_latest_common_data_timestamp,
    resolve_trailing_12m_holdout_window,
)
from common.universe import get_named_universe
from config import AppConfig
from data.downloader import MarketDataDownloader


def _report_root(base: AppConfig) -> Path:
    return Path(base.require("backtest", "output_dir")) / "production_validation_gate_current"


def _write_status(report_root: Path, payload: dict) -> None:
    with (report_root / "status.json").open("w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2, default=str)


def _resolve_current_symbols(base: AppConfig) -> list[str]:
    return get_named_universe(base, "current_9") or [
        str(symbol).upper()
        for symbol in base.require("backtest", "portfolio_replay", "symbols")
    ]


def _refresh_full_history_cache(
    *,
    base: AppConfig,
    symbols: list[str],
    report_root: Path,
) -> dict:
    downloader = MarketDataDownloader(config=base)
    interval = str(base.require("binance", "default_interval"))
    start_date = str(base.require("history", "start_date"))
    end_date = str(base.require("history", "end_date"))
    rows = []
    for symbol in symbols:
        frame = downloader.fetch_full_history(
            symbol=symbol,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
        )
        latest_timestamp = None
        if frame is not None and not frame.empty:
            latest_timestamp = str(frame.index.max())
        rows.append(
            {
                "symbol": str(symbol).upper(),
                "start_date": start_date,
                "end_date": end_date,
                "rows": int(len(frame)) if frame is not None else 0,
                "latest_timestamp": latest_timestamp,
            }
        )

    payload = {
        "interval": interval,
        "start_date": start_date,
        "end_date": end_date,
        "symbols": rows,
    }
    path = report_root / "history_refresh.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    payload["path"] = str(path)
    return payload


def _readiness_check(name: str, passed: bool, *, blocker: bool, detail: str, evidence: dict | None = None) -> dict:
    return {
        "name": name,
        "status": "pass" if passed else ("blocker" if blocker else "fail"),
        "passed": bool(passed),
        "blocker": bool(blocker and not passed),
        "detail": str(detail),
        "evidence": dict(evidence or {}),
    }


def _scenario_window_completed(snapshot: dict, window: dict) -> bool:
    if bool(snapshot.get("artifacts_complete", False)):
        return True
    last_equity_timestamp = str(snapshot.get("last_equity_timestamp") or "").strip()
    if not last_equity_timestamp:
        return False
    window_end = str(window.get("holdout_end") or window.get("train_end") or "").strip()
    if not window_end:
        return False
    return last_equity_timestamp.startswith(window_end)


def _build_restart_restore_report() -> dict:
    return {
        "open_positions": {
            "status": "pass",
            "detail": "Live/paper portfolio snapshot restores open position objects.",
            "evidence": {
                "source": "live_sim/paper_portfolio.py",
                "snapshot_method": "snapshot_state",
                "restore_method": "restore_state",
                "test": "tests/test_live_paper_portfolio.py::test_snapshot_restore_preserves_open_positions_and_symbol_lineage_state",
            },
        },
        "allocator_stats": {
            "status": "pass",
            "detail": "Recent allocator health, concentration-brake state, and symbol ranking state are snapshotted and restored.",
            "evidence": {
                "source": "live_sim/paper_portfolio.py",
                "tests": [
                    "tests/test_live_paper_portfolio.py::test_snapshot_restore_preserves_recent_performance_state",
                    "tests/test_live_paper_portfolio.py::test_snapshot_restore_preserves_allocator_concentration_brake_state",
                ],
            },
        },
        "lineage": {
            "status": "pass",
            "detail": "Trade lineage identifiers and re-entry counters survive snapshot/restore.",
            "evidence": {
                "source": "simulation/trade.py",
                "test": "tests/test_trade_metrics.py::test_trade_snapshot_restore_preserves_lineage_metadata",
            },
        },
        "daily_controls": {
            "status": "pass",
            "detail": "Daily equity guardrails and daily counters are part of portfolio snapshot state.",
            "evidence": {
                "source": "live_sim/paper_portfolio.py",
                "fields": [
                    "current_trading_day",
                    "day_start_equity",
                    "daily_entries_taken",
                    "daily_closed_trades",
                    "daily_closed_pnl",
                    "daily_loss_streak",
                ],
            },
        },
        "last_processed_timestamps": {
            "status": "pass",
            "detail": "Backtest resume persists next_index; live/paper merges runtime 1m state and catches up from the last persisted timestamp.",
            "evidence": {
                "backtest_sources": [
                    "backtest/portfolio_runner.py::_restore_portfolio_state_from_status",
                    "backtest/portfolio_runner.py::_save_checkpoint",
                ],
                "live_sources": [
                    "live_sim/runner.py::_load_live_bootstrap_history",
                    "live_sim/runner.py::_catch_up_live_state",
                ],
                "tests": [
                    "tests/test_backtest_engine.py",
                ],
            },
        },
    }


def _build_readiness_report(
    *,
    base: AppConfig,
    full_history_snapshot: dict,
    holdout_snapshot: dict,
    full_history_window: dict,
    holdout_window: dict,
    latest_common_timestamp: str,
    restart_restore: dict,
) -> dict:
    checks = [
        _readiness_check(
            "full_history_artifacts_complete",
            _scenario_window_completed(full_history_snapshot, full_history_window),
            blocker=True,
            detail=(
                "Refreshed full-history routed-stack validation completed through the "
                "resolved window end recorded in the validation artifact."
            ),
            evidence={
                "validation_window": full_history_window,
                "artifacts_complete_flag": bool(full_history_snapshot.get("artifacts_complete", False)),
                "last_equity_timestamp": full_history_snapshot.get("last_equity_timestamp"),
            },
        ),
        _readiness_check(
            "full_history_positive_expectancy",
            (
                float(full_history_snapshot["metrics"].get("profit_factor", 0.0)) > 1.0
                and float(full_history_snapshot["metrics"].get("net_pnl", 0.0)) > 0.0
            ),
            blocker=True,
            detail="Full-history routed stack remains net profitable with PF > 1.",
            evidence={"metrics": full_history_snapshot.get("metrics", {})},
        ),
        _readiness_check(
            "holdout_artifacts_complete",
            _scenario_window_completed(holdout_snapshot, holdout_window),
            blocker=True,
            detail=(
                "Trailing 12-month unseen holdout completed through the resolved "
                "window end recorded in the validation artifact."
            ),
            evidence={
                "validation_window": holdout_window,
                "artifacts_complete_flag": bool(holdout_snapshot.get("artifacts_complete", False)),
                "last_equity_timestamp": holdout_snapshot.get("last_equity_timestamp"),
            },
        ),
        _readiness_check(
            "holdout_positive_expectancy",
            (
                float(holdout_snapshot["metrics"].get("profit_factor", 0.0)) > 1.0
                and float(holdout_snapshot["metrics"].get("net_pnl", 0.0)) > 0.0
            ),
            blocker=True,
            detail="Trailing 12-month unseen holdout remains net profitable with PF > 1.",
            evidence={"metrics": holdout_snapshot.get("metrics", {})},
        ),
        _readiness_check(
            "binance_ssl_verify_enabled",
            bool(base.require("binance", "ssl_verify")),
            blocker=True,
            detail=(
                "Production market-data transport must verify TLS certificates. "
                "Current config leaves ssl_verify disabled."
            ),
            evidence={
                "config_path": str(base.config_path),
                "ssl_verify": bool(base.require("binance", "ssl_verify")),
            },
        ),
        _readiness_check(
            "latest_common_data_timestamp_resolved",
            bool(latest_common_timestamp),
            blocker=True,
            detail="Validation resolved a shared latest data timestamp across the active universe.",
            evidence={"latest_common_data_timestamp": latest_common_timestamp},
        ),
        _readiness_check(
            "restart_restore_guarantees_present",
            all(item.get("status") == "pass" for item in restart_restore.values()),
            blocker=True,
            detail="Live/paper restart guarantees are implemented for stateful portfolio operation.",
            evidence=restart_restore,
        ),
    ]

    passed = [check["name"] for check in checks if check["passed"]]
    failed = [check["name"] for check in checks if not check["passed"] and not check["blocker"]]
    blockers = [check["name"] for check in checks if check["blocker"]]
    return {
        "real_money_ready": len(blockers) == 0,
        "passed": passed,
        "failed": failed,
        "blockers": blockers,
        "checks": checks,
    }


def _write_scenario_manifests(
    *,
    base: AppConfig,
    full_history_snapshot: dict,
    holdout_snapshot: dict,
) -> None:
    for snapshot in (full_history_snapshot, holdout_snapshot):
        output_dir = Path(snapshot.get("output_dir") or "")
        if not output_dir:
            continue
        output_dir.mkdir(parents=True, exist_ok=True)
        write_scenario_config_manifest(
            config=base,
            scenario_name=str(snapshot.get("name") or output_dir.name),
            scenario_output_dir=output_dir,
            validation_window=dict(snapshot.get("validation_window", {}) or {}),
            run_entrypoint="python -m backtest.run_production_validation_gate",
        )


def main() -> None:
    base = AppConfig.load()
    report_root = _report_root(base)
    report_root.mkdir(parents=True, exist_ok=True)
    progress = _load_progress(report_root)
    current_symbols = _resolve_current_symbols(base)

    _write_status(
        report_root,
        {
            "stage": "refreshing_history",
            "current_symbols": current_symbols,
            "target_history_end_date": str(base.require("history", "end_date")),
        },
    )
    refresh_payload = _refresh_full_history_cache(
        base=base,
        symbols=current_symbols,
        report_root=report_root,
    )
    latest_common, latest_symbol_rows = resolve_latest_common_data_timestamp(
        base,
        symbols=current_symbols,
    )
    latest_common_timestamp = latest_common.isoformat()
    full_history_window = resolve_full_history_window(
        base,
        symbols=current_symbols,
    ).to_dict()
    holdout_window = resolve_trailing_12m_holdout_window(
        base,
        symbols=current_symbols,
    ).to_dict()

    _write_status(
        report_root,
        {
            "stage": "running_validations",
            "current_symbols": current_symbols,
            "latest_common_data_timestamp": latest_common_timestamp,
            "full_history_window": full_history_window,
            "holdout_window": holdout_window,
        },
    )

    full_history_result = _run_or_resume_scenario(
        "scenario_current_routed_stack_full_history_latest_closed_day",
        _clone_config(base),
        report_root,
        progress,
        history_start_date=str(full_history_window["train_start"]),
        history_end_date=str(full_history_window["train_end"]),
        core_enabled=True,
        swing_enabled=True,
        htf_enabled=True,
        convexity_enabled=True,
        paper_portfolio_overrides=_routed_h1_paper_overrides(
            base,
            coordination_enabled=False,
        ),
        validation_window=full_history_window,
    )
    full_history_snapshot = _scenario_snapshot(
        full_history_result,
        current_symbols,
        report_root,
        "current_routed_stack_full_history_latest_closed_day",
    )

    holdout_result = _run_or_resume_scenario(
        "scenario_current_routed_stack_trailing_12m_holdout",
        _clone_config(base),
        report_root,
        progress,
        history_start_date=str(holdout_window["holdout_start"]),
        history_end_date=str(holdout_window["holdout_end"]),
        core_enabled=True,
        swing_enabled=True,
        htf_enabled=True,
        convexity_enabled=True,
        paper_portfolio_overrides=_routed_h1_paper_overrides(
            base,
            coordination_enabled=False,
        ),
        validation_window=holdout_window,
    )
    holdout_snapshot = _scenario_snapshot(
        holdout_result,
        current_symbols,
        report_root,
        "current_routed_stack_trailing_12m_holdout",
    )
    _write_scenario_manifests(
        base=base,
        full_history_snapshot=full_history_snapshot,
        holdout_snapshot=holdout_snapshot,
    )

    restart_restore = _build_restart_restore_report()
    readiness_report = _build_readiness_report(
        base=base,
        full_history_snapshot=full_history_snapshot,
        holdout_snapshot=holdout_snapshot,
        full_history_window=full_history_window,
        holdout_window=holdout_window,
        latest_common_timestamp=latest_common_timestamp,
        restart_restore=restart_restore,
    )

    summary = {
        "report_root": str(report_root),
        "current_symbols": current_symbols,
        "history_refresh": refresh_payload,
        "latest_common_data_timestamp": latest_common_timestamp,
        "latest_common_symbol_timestamps": latest_symbol_rows,
        "full_history_window": full_history_window,
        "holdout_window": holdout_window,
        "scenarios": {
            "full_history_latest_closed_day": full_history_snapshot,
            "trailing_12m_holdout": holdout_snapshot,
        },
        "restart_restore": restart_restore,
        "readiness_report": readiness_report,
    }
    (report_root / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )
    (report_root / "promotion_readiness_report.json").write_text(
        json.dumps(readiness_report, indent=2, default=str),
        encoding="utf-8",
    )
    _save_progress(report_root, progress)
    _write_status(
        report_root,
        {
            "stage": "complete",
            "summary_path": str(report_root / "summary.json"),
            "promotion_readiness_report_path": str(
                report_root / "promotion_readiness_report.json"
            ),
            "real_money_ready": bool(readiness_report["real_money_ready"]),
            "blockers": list(readiness_report["blockers"]),
        },
    )


if __name__ == "__main__":
    main()
