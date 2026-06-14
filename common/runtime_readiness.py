"""Central runtime readiness and validation-artifact helpers."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import AppConfig


OFFICIAL_GATE_ROOT_NAME = "production_validation_gate_current"
REAL_MONEY_MODES = {"portfolio_live", "live_capital", "real_money"}
PAPER_MODES = {"portfolio_paper", "paper"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return None
    value = str(result.stdout or "").strip()
    return value or None


def _binance_tls_settings(config: AppConfig) -> dict[str, Any]:
    env_bundle = (
        os.getenv("BINANCE_CA_BUNDLE_PATH")
        or os.getenv("REQUESTS_CA_BUNDLE")
        or os.getenv("SSL_CERT_FILE")
    )
    configured_bundle = config.get("binance", "ca_bundle_path", default=None)
    resolved_bundle = env_bundle or configured_bundle
    resolved_bundle_path = None
    bundle_exists = None
    if resolved_bundle:
        candidate = Path(str(resolved_bundle))
        if not candidate.is_absolute():
            candidate = config.root_dir / candidate
        resolved_bundle_path = str(candidate)
        bundle_exists = candidate.exists()
    ssl_verify = bool(config.get("binance", "ssl_verify", default=True))
    effective_verify = str(resolved_bundle_path) if resolved_bundle_path else ssl_verify
    return {
        "ssl_verify": ssl_verify,
        "configured_ca_bundle_path": configured_bundle,
        "env_ca_bundle_path": env_bundle,
        "resolved_ca_bundle_path": resolved_bundle_path,
        "resolved_ca_bundle_exists": bundle_exists,
        "effective_verify": effective_verify,
    }


def _scenario_output_dir(base: AppConfig, scenario_name: str) -> Path:
    return base.path("backtest", "output_dir") / OFFICIAL_GATE_ROOT_NAME / scenario_name


def _active_and_disabled_sleeves(config: AppConfig) -> tuple[list[str], list[str]]:
    active: list[str] = []
    disabled: list[str] = []

    allowed_edge_types = list(
        config.get("live_sim", "paper_portfolio", "allowed_edge_types", default=[]) or []
    )
    if "__no_core__" in {str(value) for value in allowed_edge_types}:
        disabled.append("core")
    else:
        active.append("core")

    swing_enabled = bool(
        config.get("strategy", "moonshots", "swing", "enabled", default=False)
    )
    (active if swing_enabled else disabled).append("swing_moonshot")

    for sleeve in (
        "h1_execution",
        "htf_12h_standard",
        "htf_12h_moonshot",
        "htf_12h_rotation",
        "h6_standard",
        "h6_moonshot",
    ):
        enabled = bool(config.get("strategy", sleeve, "enabled", default=False))
        (active if enabled else disabled).append(sleeve)

    return active, disabled


def _allocator_settings(config: AppConfig) -> dict[str, Any]:
    paper = dict(config.get("live_sim", "paper_portfolio", default={}) or {})
    allocator = dict(paper.get("allocator_v2", {}) or {})
    return {
        "enabled": bool(allocator.get("enabled", False)),
        "leader_dominance": dict(allocator.get("leader_dominance", {}) or {}),
        "agreement_bonus": dict(allocator.get("agreement_bonus", {}) or {}),
        "cross_sleeve_coordination": dict(
            allocator.get("cross_sleeve_coordination", {}) or {}
        ),
        "concentration_brake": dict(allocator.get("concentration_brake", {}) or {}),
        "sleeves": dict(allocator.get("sleeves", {}) or {}),
    }


def _key_risk_settings(config: AppConfig) -> dict[str, Any]:
    paper = dict(config.get("live_sim", "paper_portfolio", default={}) or {})
    daily = dict(config.get("strategy", "daily_controls", default={}) or {})
    return {
        "initial_equity": config.get("account", "initial_equity"),
        "risk_per_trade": config.get("account", "risk_per_trade"),
        "max_total_risk_fraction": paper.get("max_total_risk_fraction"),
        "min_risk_per_trade": paper.get("min_risk_per_trade"),
        "max_risk_per_trade": paper.get("max_risk_per_trade"),
        "max_trades_per_asset": paper.get("max_trades_per_asset"),
        "max_same_direction_positions": paper.get("max_same_direction_positions"),
        "max_new_positions_per_step": paper.get("max_new_positions_per_step"),
        "daily_controls": daily,
    }


def build_scenario_config_manifest(
    *,
    config: AppConfig,
    scenario_name: str,
    scenario_output_dir: Path,
    validation_window: dict[str, Any] | None,
    run_entrypoint: str,
    generated_from_existing_artifacts: bool = False,
) -> dict[str, Any]:
    current_symbols = list(config.get("universe", "symbol_sets", "current_9", default=[]) or [])
    active_sleeves, disabled_sleeves = _active_and_disabled_sleeves(config)
    strategy_allowed_sides = dict(
        config.get("live_sim", "paper_portfolio", "strategy_allowed_sides", default={}) or {}
    )
    manifest = {
        "scenario_name": scenario_name,
        "run_entrypoint": run_entrypoint,
        "generated_at_utc": _utc_now_iso(),
        "generated_from_existing_artifacts": bool(generated_from_existing_artifacts),
        "git_commit": _git_commit(config.root_dir),
        "python_version": sys.version,
        "platform": platform.platform(),
        "current_universe_symbols": current_symbols,
        "active_sleeves": active_sleeves,
        "disabled_sleeves": disabled_sleeves,
        "allocator_settings": _allocator_settings(config),
        "key_risk_settings": _key_risk_settings(config),
        "allowed_sides": list(
            config.get("live_sim", "paper_portfolio", "allowed_sides", default=[]) or []
        ),
        "strategy_allowed_sides": strategy_allowed_sides,
        "window_policy": (validation_window or {}).get("window_policy"),
        "train_start": (validation_window or {}).get("train_start"),
        "train_end": (validation_window or {}).get("train_end"),
        "holdout_start": (validation_window or {}).get("holdout_start"),
        "holdout_end": (validation_window or {}).get("holdout_end"),
        "latest_data_timestamp": (validation_window or {}).get("latest_data_timestamp"),
        "resolved_at_utc": (validation_window or {}).get("resolved_at_utc"),
        "config_hashes": {
            "settings_json_sha256": _sha256_file(config.config_path),
            "settings_py_sha256": _sha256_file(config.root_dir / "config" / "settings.py"),
        },
        "source_file_hashes": {
            "backtest/run_production_validation_gate.py": _sha256_file(
                config.root_dir / "backtest" / "run_production_validation_gate.py"
            ),
            "backtest/validate_htf_12h.py": _sha256_file(
                config.root_dir / "backtest" / "validate_htf_12h.py"
            ),
            "backtest/validate_allocator_coordination_portfolio.py": _sha256_file(
                config.root_dir / "backtest" / "validate_allocator_coordination_portfolio.py"
            ),
            "live_sim/paper_portfolio.py": _sha256_file(
                config.root_dir / "live_sim" / "paper_portfolio.py"
            ),
            "entry/h1_execution.py": _sha256_file(
                config.root_dir / "entry" / "h1_execution.py"
            ),
            "entry/htf_moonshot.py": _sha256_file(
                config.root_dir / "entry" / "htf_moonshot.py"
            ),
            "entry/htf_rotation.py": _sha256_file(
                config.root_dir / "entry" / "htf_rotation.py"
            ),
        },
        "scenario_output_dir": str(scenario_output_dir),
    }
    return manifest


def write_scenario_config_manifest(
    *,
    config: AppConfig,
    scenario_name: str,
    scenario_output_dir: Path,
    validation_window: dict[str, Any] | None,
    run_entrypoint: str,
    generated_from_existing_artifacts: bool = False,
) -> Path:
    manifest = build_scenario_config_manifest(
        config=config,
        scenario_name=scenario_name,
        scenario_output_dir=scenario_output_dir,
        validation_window=validation_window,
        run_entrypoint=run_entrypoint,
        generated_from_existing_artifacts=generated_from_existing_artifacts,
    )
    path = scenario_output_dir / "scenario_config_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return path


def load_gate_artifacts(config: AppConfig | None = None) -> dict[str, Any]:
    config = config or AppConfig.load()
    backtest_output = config.path("backtest", "output_dir")
    gate_root = (
        backtest_output / OFFICIAL_GATE_ROOT_NAME
        if backtest_output is not None
        else config.root_dir / "backtest" / "output" / OFFICIAL_GATE_ROOT_NAME
    )
    artifacts = {
        "gate_root": gate_root,
        "status_path": gate_root / "status.json",
        "summary_path": gate_root / "summary.json",
        "promotion_readiness_report_path": gate_root / "promotion_readiness_report.json",
    }
    artifacts["status"] = _safe_read_json(artifacts["status_path"])
    artifacts["summary"] = _safe_read_json(artifacts["summary_path"])
    artifacts["promotion_readiness_report"] = _safe_read_json(
        artifacts["promotion_readiness_report_path"]
    )
    return artifacts


def ensure_official_gate_manifests(config: AppConfig | None = None) -> list[Path]:
    config = config or AppConfig.load()
    artifacts = load_gate_artifacts(config)
    summary = artifacts.get("summary") or {}
    if not summary:
        return []
    written: list[Path] = []
    for scenario_key, snapshot in dict(summary.get("scenarios", {}) or {}).items():
        scenario_name = str(snapshot.get("name") or "")
        if not scenario_name:
            continue
        output_dir = Path(snapshot.get("output_dir") or _scenario_output_dir(config, scenario_name))
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / "scenario_config_manifest.json"
        if target.exists():
            continue
        manifest_path = write_scenario_config_manifest(
            config=config,
            scenario_name=scenario_name,
            scenario_output_dir=output_dir,
            validation_window=dict(snapshot.get("validation_window", {}) or {}),
            run_entrypoint="python -m backtest.run_production_validation_gate",
            generated_from_existing_artifacts=True,
        )
        written.append(manifest_path)
    return written


def _runtime_config_snapshot(config: AppConfig) -> dict[str, Any]:
    active_sleeves, disabled_sleeves = _active_and_disabled_sleeves(config)
    return {
        "current_universe_symbols": list(
            config.get("universe", "symbol_sets", "current_9", default=[]) or []
        ),
        "active_sleeves": active_sleeves,
        "disabled_sleeves": disabled_sleeves,
        "allowed_sides": list(
            config.get("live_sim", "paper_portfolio", "allowed_sides", default=[]) or []
        ),
        "strategy_allowed_sides": dict(
            config.get("live_sim", "paper_portfolio", "strategy_allowed_sides", default={}) or {}
        ),
        "allocator_v2_enabled": bool(
            config.get("live_sim", "paper_portfolio", "allocator_v2", "enabled", default=False)
        ),
        "mode": str(config.get("live_sim", "mode", default="portfolio_paper") or "portfolio_paper"),
    }


def _holdout_is_thin(summary: dict[str, Any]) -> bool:
    holdout = dict(dict(summary.get("scenarios", {}) or {}).get("trailing_12m_holdout", {}) or {})
    metrics = dict(holdout.get("metrics", {}) or {})
    if not metrics:
        return True
    profit_factor = float(metrics.get("profit_factor", 0.0) or 0.0)
    net_pnl = float(metrics.get("net_pnl", 0.0) or 0.0)
    avg_r = float(metrics.get("avg_R", 0.0) or 0.0)
    median_daily = float(metrics.get("median_daily_pnl", 0.0) or 0.0)
    return profit_factor <= 1.05 or net_pnl <= 250.0 or avg_r <= 0.0 or median_daily <= 0.0


def _classification(summary: dict[str, Any], report: dict[str, Any], blockers: list[str]) -> str:
    checks = {str(row.get("name")): bool(row.get("passed")) for row in list(report.get("checks") or [])}
    full_pass = checks.get("full_history_positive_expectancy", False)
    holdout_pass = checks.get("holdout_positive_expectancy", False)
    if not full_pass or not holdout_pass:
        return "blocked"
    if _holdout_is_thin(summary):
        return "paper-only"
    if blockers:
        return "paper-mature"
    return "tiny-real-money-pilot-eligible-after-operational-blockers-fixed"


def build_runtime_readiness(config: AppConfig | None = None, *, mode: str | None = None) -> dict[str, Any]:
    config = config or AppConfig.load()
    artifacts = load_gate_artifacts(config)
    status = artifacts.get("status") or {}
    summary = artifacts.get("summary") or {}
    report = artifacts.get("promotion_readiness_report") or {}
    if summary:
        ensure_official_gate_manifests(config)
        artifacts = load_gate_artifacts(config)
        summary = artifacts.get("summary") or {}
        report = artifacts.get("promotion_readiness_report") or {}
    tls = _binance_tls_settings(config)
    runtime_config = _runtime_config_snapshot(config)
    blockers: list[str] = []
    warnings: list[str] = []

    if not status:
        blockers.append("missing_status_json")
    if not summary:
        blockers.append("missing_summary_json")
    if not report:
        blockers.append("missing_promotion_readiness_report_json")

    if status and str(status.get("stage")) != "complete":
        blockers.append("validation_gate_not_complete")

    checks = {str(row.get("name")): dict(row) for row in list(report.get("checks") or [])}
    if report and checks:
        if not bool(checks.get("full_history_artifacts_complete", {}).get("passed")):
            blockers.append("full_history_artifacts_incomplete")
        if not bool(checks.get("full_history_positive_expectancy", {}).get("passed")):
            blockers.append("full_history_failed")
        if not bool(checks.get("holdout_artifacts_complete", {}).get("passed")):
            blockers.append("holdout_artifacts_incomplete")
        if not bool(checks.get("holdout_positive_expectancy", {}).get("passed")):
            blockers.append("holdout_failed")
        if not bool(checks.get("restart_restore_guarantees_present", {}).get("passed")):
            blockers.append("restart_restore_missing")
    elif report:
        blockers.append("missing_readiness_checks")

    if not tls["ssl_verify"]:
        blockers.append("ssl_verification_disabled")
        warnings.append("Binance TLS verification is disabled. Paper mode may run, live-capital mode must remain blocked.")
    if tls["resolved_ca_bundle_path"] and tls["resolved_ca_bundle_exists"] is False:
        blockers.append("ca_bundle_missing")

    manifest_mismatches: list[str] = []
    scenario_manifest_paths: dict[str, str] = {}
    if summary:
        for scenario_key, snapshot in dict(summary.get("scenarios", {}) or {}).items():
            scenario_name = str(snapshot.get("name") or "")
            output_dir = (
                Path(snapshot.get("output_dir"))
                if snapshot.get("output_dir")
                else _scenario_output_dir(config, scenario_name)
            )
            manifest_path = output_dir / "scenario_config_manifest.json"
            scenario_manifest_paths[scenario_key] = str(manifest_path)
            manifest = _safe_read_json(manifest_path)
            if manifest is None:
                manifest_mismatches.append(f"{scenario_key}:missing_manifest")
                continue
            if list(manifest.get("current_universe_symbols") or []) != list(
                runtime_config["current_universe_symbols"]
            ):
                manifest_mismatches.append(f"{scenario_key}:universe_symbols")
            if list(manifest.get("active_sleeves") or []) != list(runtime_config["active_sleeves"]):
                manifest_mismatches.append(f"{scenario_key}:active_sleeves")
            if list(manifest.get("disabled_sleeves") or []) != list(runtime_config["disabled_sleeves"]):
                manifest_mismatches.append(f"{scenario_key}:disabled_sleeves")
            if bool(dict(manifest.get("allocator_settings") or {}).get("enabled")) != bool(
                runtime_config["allocator_v2_enabled"]
            ):
                manifest_mismatches.append(f"{scenario_key}:allocator_v2_enabled")
            manifest_strategy_sides = dict(manifest.get("strategy_allowed_sides") or {})
            if manifest_strategy_sides != dict(runtime_config["strategy_allowed_sides"]):
                manifest_mismatches.append(f"{scenario_key}:strategy_allowed_sides")
        if manifest_mismatches:
            blockers.append("validated_config_mismatch")

    latest_common_timestamp = str(summary.get("latest_common_data_timestamp") or "") if summary else ""
    if summary and not latest_common_timestamp:
        blockers.append("latest_common_timestamp_missing")

    classification = _classification(summary, report, blockers)
    paper_allowed = bool(status) and bool(summary) and bool(report) and "validation_gate_not_complete" not in blockers and "full_history_failed" not in blockers and "holdout_failed" not in blockers and "restart_restore_missing" not in blockers
    real_money_allowed = (
        classification == "tiny-real-money-pilot-eligible-after-operational-blockers-fixed"
        and len(blockers) == 0
    )

    requested_mode = str(mode or runtime_config["mode"]).lower()
    if requested_mode in REAL_MONEY_MODES and not real_money_allowed:
        warnings.append("Real-money mode is fail-closed until validation, config compatibility, and operational readiness all pass.")

    blockers = list(dict.fromkeys(blockers))
    warnings = list(dict.fromkeys(warnings))

    return {
        "requested_mode": requested_mode,
        "gate_root": str(artifacts["gate_root"]),
        "status_path": str(artifacts["status_path"]),
        "status": status,
        "summary_path": str(artifacts["summary_path"]),
        "promotion_readiness_report_path": str(artifacts["promotion_readiness_report_path"]),
        "classification": classification,
        "paper_runtime_allowed": paper_allowed,
        "real_money_allowed": real_money_allowed,
        "blockers": blockers,
        "warnings": warnings,
        "latest_common_data_timestamp": latest_common_timestamp,
        "validated_boundary": latest_common_timestamp,
        "holdout_is_thin": _holdout_is_thin(summary) if summary else True,
        "runtime_config": runtime_config,
        "tls": tls,
        "scenario_manifest_paths": scenario_manifest_paths,
        "manifest_mismatches": manifest_mismatches,
    }


def assert_runtime_mode_ready(config: AppConfig | None = None, *, mode: str | None = None) -> dict[str, Any]:
    config = config or AppConfig.load()
    readiness = build_runtime_readiness(config, mode=mode)
    requested_mode = str(readiness["requested_mode"]).lower()
    if requested_mode in REAL_MONEY_MODES:
        if not readiness["real_money_allowed"]:
            blocker_text = ", ".join(readiness["blockers"])
            if not blocker_text:
                blocker_text = f"classification:{readiness.get('classification', 'unknown')}"
            raise RuntimeError(
                "Real-money mode refused startup because readiness is not satisfied: "
                f"{blocker_text}"
            )
        raise RuntimeError(
            "Real-money execution adapter is not enabled in this repository. "
            "Readiness may be satisfied, but deployment remains disabled."
        )
    return readiness
