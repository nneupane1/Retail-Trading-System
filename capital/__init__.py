from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from .capital_lanes import DEFAULT_CAPITAL_LANES, default_lane_payload
from .capital_promotion_review import build_capital_promotion_review

CAPITAL_REFACTOR_LAYERS = [
    "capital_lanes",
    "risk_bands",
    "lifecycle",
    "opportunity_cost",
    "shadow_rejection_book",
    "winner_forensics",
    "capital_recycling",
    "regime_multiplier",
    "portfolio_heat",
    "promotion_review",
]


def capital_refactor_enabled(config) -> bool:
    getter = getattr(config, "get", None)
    if not callable(getter):
        return False
    return bool(getter("capital_refactor", "enabled", default=False))


def layer_enabled(config, layer_name: str) -> bool:
    getter = getattr(config, "get", None)
    if not callable(getter):
        return False
    root_enabled = capital_refactor_enabled(config)
    layer_flag = bool(getter("capital_refactor", layer_name, "enabled", default=False))
    return bool(root_enabled and layer_flag)


def behavior_change_allowed(config) -> bool:
    return False


def scaffold_inventory_path(config) -> Path:
    output_dir = Path(config.require("live_sim", "output_dir"))
    return output_dir / "capital_refactor" / "scaffold_inventory.json"


def build_scaffold_layer_statuses(config) -> dict[str, dict[str, object]]:
    return {
        layer_name: {
            "present": True,
            "enabled": layer_enabled(config, layer_name),
            "behavior_change_allowed": False,
        }
        for layer_name in CAPITAL_REFACTOR_LAYERS
    }


def build_scaffold_inventory_payload(config, readiness: dict[str, object] | None = None) -> dict[str, object]:
    readiness = dict(readiness or {})
    promotion_review = build_capital_promotion_review()
    return {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "classification": readiness.get("classification"),
        "paper_runtime_allowed": bool(readiness.get("paper_runtime_allowed")),
        "real_money_allowed": False,
        "validated_boundary": readiness.get("validated_boundary"),
        "ssl_verify": bool((readiness.get("tls") or {}).get("ssl_verify", False)),
        "capital_refactor_enabled": capital_refactor_enabled(config),
        "behavior_change_allowed": behavior_change_allowed(config),
        "modules_present": {
            "capital_lanes": True,
            "risk_bands": True,
            "lifecycle_state_machine": True,
            "opportunity_cost": True,
            "shadow_rejection_book": True,
            "winner_forensics": True,
            "capital_recycling": True,
            "regime_capital_multiplier": True,
            "portfolio_heat": True,
            "capital_promotion_review": True,
        },
        "layer_statuses": build_scaffold_layer_statuses(config),
        "default_capital_lanes": default_lane_payload(),
        "promotion_review": promotion_review,
        "config_path": str(getattr(config, "config_path", "")),
        "warning": "scaffold_only_no_trading_behavior_change",
    }


def write_scaffold_inventory(config, readiness: dict[str, object] | None = None) -> Path:
    path = scaffold_inventory_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_scaffold_inventory_payload(config, readiness=readiness), indent=2),
        encoding="utf-8",
    )
    return path


__all__ = [
    "CAPITAL_REFACTOR_LAYERS",
    "DEFAULT_CAPITAL_LANES",
    "behavior_change_allowed",
    "build_capital_promotion_review",
    "build_scaffold_inventory_payload",
    "build_scaffold_layer_statuses",
    "capital_refactor_enabled",
    "layer_enabled",
    "scaffold_inventory_path",
    "write_scaffold_inventory",
]
