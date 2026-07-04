from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from structural_compounding_lab.common.project_paths import package_root, project_root, resolve_project_path


COURT_NAME = "USDT_SIGNAL_USDC_EXECUTION_FREEZE_MANIFEST"
OUTPUT_FOLDER_NAME = "usdt_signal_usdc_execution_freeze_manifest_001"
CLASSIFICATION = "USDT_SIGNAL_USDC_EXECUTION_2PCT_GUARDED_CANDIDATE_FROZEN_RESEARCH_ONLY"

SAFETY_FLAGS = {
    "research_only": True,
    "paper_validation_ready": False,
    "paper_allowed": False,
    "live_allowed": False,
    "real_money_allowed": False,
    "order_path_created": False,
    "broker_path_created": False,
    "account_endpoint_used": False,
    "order_endpoint_used": False,
    "signed_endpoint_used": False,
    "private_endpoint_used": False,
    "strategy_logic_changed": False,
    "entries_changed": False,
    "exits_changed": False,
    "thresholds_tuned": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _eur(value: Any) -> str:
    return f"€{float(value):,.2f}"


def _write_report(output_root: Path, manifest: dict[str, Any]) -> None:
    rec = manifest["frozen_allocator_candidate"]
    bridge = manifest["frozen_usdt_signal_usdc_execution_reference"]
    lines = [
        "# USDT Signal → USDC Execution Freeze Manifest 001",
        "",
        f"- Final classification: `{manifest['final_classification']}`",
        "- Freeze scope: research candidate + execution guard, not live trading.",
        "- Production order path remains disabled.",
        "",
        "## Frozen candidate",
        "",
        f"- Signal source: `{manifest['signal_source_quote']}`",
        f"- Execution quote: `{manifest['execution_quote']}`",
        f"- Universe: `{', '.join(manifest['frozen_symbol_map'].keys())}`",
        f"- Allocator: `{rec['variant_id']}`",
        "- Max slots from start: `2`",
        "- Max risk per trade: `1%`",
        "- Max total open portfolio risk from start: `2%`",
        "",
        "## Evidence",
        "",
        f"- USDC bridge research after cost + yearly tax reserve: `{_eur(bridge['research_equity_after_tax'])}`",
        f"- USDC bridge holdout after cost + yearly tax reserve: `{_eur(bridge['holdout_equity_after_tax'])}`",
        f"- Recommended allocator research: `{_eur(rec['research_equity_after_tax'])}`",
        f"- Recommended allocator holdout: `{_eur(rec['holdout_equity_after_tax'])}`",
        f"- Recommended allocator holdout PF: `{float(rec['holdout_profit_factor']):.2f}`",
        f"- Recommended allocator holdout DD: `{float(rec['holdout_max_drawdown_after_tax']) * 100:.2f}%`",
        "",
        "## Guard requirement",
        "",
        "- The live bridge must pass the USDT→USDC execution guard before any order adapter may receive an order request.",
        "- Guard checks: frozen symbol map, BUY-only spot, fresh USDT/USDC closed 1m candles, price deviation, USDC spread, orderbook depth, and tiny-smoke notional cap.",
        "",
        "## Safety",
        "",
        "- `paper_validation_ready=false`",
        "- `live_allowed=false`",
        "- `real_money_allowed=false`",
        "- `order_path_created=false`",
        "- `broker_path_created=false`",
    ]
    (output_root / "USDT_SIGNAL_USDC_EXECUTION_FREEZE_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(output_root: Path | None = None) -> dict[str, Any]:
    pkg = package_root()
    output_root = output_root or pkg / "output" / OUTPUT_FOLDER_NAME
    paths = {
        "usdt_signal_usdc_execution_realistic_capped_summary": pkg
        / "output"
        / "usdt_signal_usdc_execution_realistic_capped_court_001"
        / "usdt_signal_usdc_execution_realistic_capped_summary.json",
        "allocator_frequency_summary": pkg
        / "output"
        / "usdc_spot_allocator_frequency_court_001"
        / "usdc_spot_allocator_frequency_summary.json",
        "execution_guard_report": pkg / "output" / "usdt_usdc_execution_guard" / "usdt_usdc_execution_guard_report.json",
        "symbol_cap_manifest": pkg
        / "output"
        / "multi_symbol_btc_exact_fill_cap_calibration_court_001"
        / "nine_symbol_recommended_symbol_caps_manifest.json",
        "execution_guard_source": pkg / "execution" / "usdt_usdc_execution_guard.py",
        "allocator_frequency_source": pkg / "diagnostics" / "usdc_spot_allocator_frequency_court.py",
    }
    missing = {name: str(path) for name, path in paths.items() if not path.exists()}
    if missing:
        manifest = {
            "court_name": COURT_NAME,
            "created_at_utc": _now(),
            "final_classification": "USDT_SIGNAL_USDC_EXECUTION_FREEZE_BLOCKED_MISSING_ARTIFACTS",
            "missing_artifacts": missing,
            **SAFETY_FLAGS,
        }
        _write_json(output_root / "usdt_signal_usdc_execution_freeze_manifest.json", manifest)
        return manifest

    bridge = _read_json(paths["usdt_signal_usdc_execution_realistic_capped_summary"])
    allocator = _read_json(paths["allocator_frequency_summary"])
    guard = _read_json(paths["execution_guard_report"])
    cap_manifest = _read_json(paths["symbol_cap_manifest"])
    rec = allocator["recommended_risk_adjusted_candidate"]
    guard_decision = guard["decision"]
    frozen_map = {
        "ADAUSDT": "ADAUSDC",
        "AVAXUSDT": "AVAXUSDC",
        "BNBUSDT": "BNBUSDC",
        "BTCUSDT": "BTCUSDC",
        "DOGEUSDT": "DOGEUSDC",
        "ETHUSDT": "ETHUSDC",
        "LINKUSDT": "LINKUSDC",
        "SOLUSDT": "SOLUSDC",
        "XRPUSDT": "XRPUSDC",
    }
    gates = {
        "bridge_court_passed": bridge.get("final_classification")
        == "USDT_SIGNAL_USDC_EXECUTION_REALISTIC_CAPPED_VALIDATED_RESEARCH_ONLY",
        "allocator_court_passed": allocator.get("final_classification")
        == "USDC_SPOT_ALLOCATOR_FREQUENCY_IMPROVED_RESEARCH_ONLY",
        "risk_adjusted_candidate_is_2pct": rec.get("variant_id") == "early_two_1pct_each_total_2pct",
        "guard_public_check_passed_no_order": guard_decision.get("classification")
        == "USDT_TO_USDC_EXECUTION_GUARD_PASSED_NO_ORDER_SENT",
        "guard_sent_no_order": guard_decision.get("order_sent") is False,
        "real_money_disabled": not any(bool(bridge.get(k)) for k in ("live_allowed", "real_money_allowed", "order_path_created", "broker_path_created")),
        "paper_validation_ready_false": bridge.get("paper_validation_ready") is False,
    }
    classification = CLASSIFICATION if all(gates.values()) else "USDT_SIGNAL_USDC_EXECUTION_FREEZE_BLOCKED_GATE_FAILED"
    manifest = {
        "court_name": COURT_NAME,
        "created_at_utc": _now(),
        "final_classification": classification,
        "freeze_scope": "USDT signal source with USDC spot-long execution bridge and 2% total-open-risk allocator",
        "signal_source_quote": "USDT",
        "execution_quote": "USDC",
        "frozen_symbol_map": frozen_map,
        "frozen_allocator_candidate": {
            "variant_id": rec["variant_id"],
            "research_equity_after_tax": rec["research"]["ending_total_equity_after_tax"],
            "holdout_equity_after_tax": rec["holdout"]["ending_total_equity_after_tax"],
            "research_selected_trades": rec["research"]["selected_trades"],
            "holdout_selected_trades": rec["holdout"]["selected_trades"],
            "holdout_profit_factor": rec["holdout"]["profit_factor"],
            "holdout_max_drawdown_after_tax": rec["holdout"]["max_drawdown_total_after_tax"],
            "max_total_open_risk_from_start": 0.02,
            "max_risk_per_trade": 0.01,
            "max_slots_from_start": 2,
        },
        "frozen_usdt_signal_usdc_execution_reference": {
            "research_equity_after_tax": bridge["comparison_to_canonical_usdt"]["spot_long_only_execution_bridge"][
                "research_equity_after_tax"
            ],
            "holdout_equity_after_tax": bridge["comparison_to_canonical_usdt"]["spot_long_only_execution_bridge"][
                "holdout_equity_after_tax"
            ],
            "canonical_usdt_research_after_cost_tax_eur": bridge["canonical_usdt_reference"][
                "canonical_research_equity_after_tax"
            ],
            "canonical_usdt_holdout_after_cost_tax_eur": bridge["canonical_usdt_reference"][
                "canonical_holdout_equity_after_tax"
            ],
        },
        "execution_guard": {
            "required_before_any_order_adapter": True,
            "latest_public_guard_classification": guard_decision.get("classification"),
            "latest_public_guard_accepted": guard_decision.get("accepted"),
            "latest_public_guard_order_sent": guard_decision.get("order_sent"),
            "latest_public_guard_real_money_allowed": guard_decision.get("real_money_allowed"),
        },
        "symbol_caps_eur": cap_manifest["recommended_symbol_caps_eur"],
        "gate": gates,
        "source_artifacts": {name: str(path) for name, path in paths.items()},
        "source_hashes": {name: _sha256(path) for name, path in paths.items()},
        **SAFETY_FLAGS,
    }
    _write_json(output_root / "usdt_signal_usdc_execution_freeze_manifest.json", manifest)
    _write_report(output_root, manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=COURT_NAME)
    parser.add_argument("--output-dir", default=f"structural_compounding_lab/output/{OUTPUT_FOLDER_NAME}")
    args = parser.parse_args()
    manifest = run(resolve_project_path(args.output_dir))
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    project_root()
    main()
