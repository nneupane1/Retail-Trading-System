from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


ROOT_PATH = Path(__file__).resolve().parents[1]
DEFAULT_SCAFFOLD_CONFIG = {
    "market_structure_refactor": {
        "enabled": False,
        "support_resistance": {
            "enabled": False,
            "display_only": True,
        },
        "liquidity_zones": {
            "enabled": False,
            "display_only": True,
        },
        "market_structure_context": {
            "enabled": False,
            "display_only": True,
        },
        "strategy_authority_allowed": False,
        "behavior_change_allowed": False,
    }
}


def scaffold_config_path(root_dir: Path | None = None) -> Path:
    base = Path(root_dir).resolve() if root_dir is not None else ROOT_PATH
    return base / "config" / "market_structure_scaffold.json"


def load_scaffold_config(root_dir: Path | None = None) -> dict[str, Any]:
    path = scaffold_config_path(root_dir)
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_SCAFFOLD_CONFIG))
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        return json.loads(json.dumps(DEFAULT_SCAFFOLD_CONFIG))
    return payload


def scaffold_inventory_path(root_dir: Path | None = None) -> Path:
    base = Path(root_dir).resolve() if root_dir is not None else ROOT_PATH
    return base / "backtest" / "output" / "market_structure" / "scaffold_inventory.json"


def build_scaffold_inventory_payload(root_dir: Path | None = None) -> dict[str, Any]:
    config = load_scaffold_config(root_dir)
    root = config.get("market_structure_refactor", {})
    return {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "scaffold": "market_structure_support_resistance_liquidity",
        "enabled": bool(root.get("enabled", False)),
        "behavior_change_allowed": False,
        "entry_behavior_changed": False,
        "exit_behavior_changed": False,
        "allocator_behavior_changed": False,
        "risk_behavior_changed": False,
        "sizing_behavior_changed": False,
        "thresholds_changed": False,
        "real_money_allowed": False,
        "display_only": True,
        "future_research_only": True,
        "modules_present": {
            "support_resistance": True,
            "liquidity_zones": True,
            "market_structure_context": True,
            "scaffold_inventory": True,
        },
        "config_path": str(scaffold_config_path(root_dir)),
        "config": config,
        "warning": "market_structure_scaffold_only_no_trading_behavior_change",
    }


def write_scaffold_inventory(root_dir: Path | None = None) -> Path:
    path = scaffold_inventory_path(root_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_scaffold_inventory_payload(root_dir)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path

