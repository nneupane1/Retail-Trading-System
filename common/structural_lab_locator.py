from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

ROOT_PATH = Path(__file__).resolve().parents[1]
STRUCTURAL_LAB_ENV_VAR = "STRUCTURAL_COMPOUNDING_LAB_ROOT"
STRUCTURAL_LAB_MANIFEST = Path("config") / "structural_compounding_lab_project.json"

_SETTINGS_DEFAULTS: dict[str, Any] = {
    "lab_name": "Structural Compounding Lab",
    "research_only": True,
    "read_only_frontend": True,
    "symbol": "BTCUSDT",
    "visual_timeframes": ["1h", "4h", "12h", "1d"],
    "data": {
        "base_path": "../data_storage",
        "default_interval": "1m",
        "history_start_date": "2018-01-01",
        "history_end_date": "2026-06-13",
        "analysis_start_date": None,
        "analysis_end_date": None,
    },
    "output": {"path": "output"},
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _normalize_project_root(candidate: str | Path | None) -> Path | None:
    if candidate is None:
        return None
    path = Path(str(candidate)).expanduser()
    if not path.is_absolute():
        path = (ROOT_PATH / path).resolve()
    return path


def _manifest_project_root(base_root: Path) -> Path | None:
    manifest_path = base_root / STRUCTURAL_LAB_MANIFEST
    if not manifest_path.exists():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    project_root = _normalize_project_root(payload.get("project_root"))
    if project_root is None:
        return None
    return project_root


def _git_project_root(start: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return _normalize_project_root(result.stdout.strip())


def _candidate_project_roots(root_dir: Path | None = None) -> list[Path]:
    base_root = Path(root_dir) if root_dir is not None else ROOT_PATH
    candidates: list[Path] = []

    env_root = _normalize_project_root(os.getenv(STRUCTURAL_LAB_ENV_VAR))
    if env_root is not None:
        candidates.append(env_root)

    if root_dir is not None:
        candidates.append(base_root)

    git_root = _git_project_root(Path.cwd())
    if git_root is not None:
        candidates.append(git_root)

    cwd = Path.cwd().resolve()
    candidates.extend([cwd, *cwd.parents])

    candidates.append(base_root)

    if base_root != ROOT_PATH and (ROOT_PATH / "structural_compounding_lab").exists():
        candidates.append(ROOT_PATH)

    manifest_root = _manifest_project_root(base_root)
    if manifest_root is not None:
        candidates.append(manifest_root)

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def resolve_structural_lab_project_root(root_dir: Path | None = None) -> Path:
    for candidate in _candidate_project_roots(root_dir):
        package_root = candidate / "structural_compounding_lab"
        if package_root.exists():
            return candidate
    return (Path(root_dir) if root_dir is not None else ROOT_PATH)


def structural_lab_package_root(root_dir: Path | None = None) -> Path:
    return resolve_structural_lab_project_root(root_dir) / "structural_compounding_lab"


def structural_lab_output_root(root_dir: Path | None = None) -> Path:
    return structural_lab_package_root(root_dir) / "output"


def structural_lab_settings_paths(root_dir: Path | None = None) -> dict[str, Path]:
    package_root = structural_lab_package_root(root_dir)
    return {
        "json": package_root / "config" / "structural_compounding_settings.json",
        "yaml": package_root / "config" / "structural_compounding_settings.yaml",
        "symbols": package_root / "config" / "symbols.json",
    }


def _load_yaml_if_available(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_structural_lab_settings_data(root_dir: Path | None = None) -> dict[str, Any]:
    settings_paths = structural_lab_settings_paths(root_dir)
    payload: dict[str, Any] = {}
    if settings_paths["json"].exists():
        try:
            raw = json.loads(settings_paths["json"].read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                payload = raw
        except Exception:
            payload = {}
    elif settings_paths["yaml"].exists():
        payload = _load_yaml_if_available(settings_paths["yaml"])
    return _deep_merge(_SETTINGS_DEFAULTS, payload)
