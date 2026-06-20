from __future__ import annotations

import csv
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_AUDIT = ROOT / "migration_audit"
STRUCTURAL_OUTPUT = ROOT / "structural_compounding_lab" / "output"
STRUCTURAL_DATA = ROOT / "structural_compounding_lab" / "data_storage"
ROOT_DATA = ROOT / "data_storage"


def _run(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True, encoding="utf-8", errors="replace")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not fieldnames:
        keys: list[str] = []
        for row in rows:
            for key in row.keys():
                if key not in keys:
                    keys.append(key)
        fieldnames = keys
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _git_lines(*args: str) -> list[str]:
    output = _run("git", *args)
    return [line.rstrip("\n") for line in output.splitlines()]


TRACKED = set(_git_lines("ls-files"))
UNTRACKED = set(_git_lines("ls-files", "--others", "--exclude-standard"))
IGNORED = set(_git_lines("ls-files", "--others", "-i", "--exclude-standard"))


def _git_state(path: Path) -> tuple[bool, bool, bool]:
    rel = path.relative_to(ROOT).as_posix()
    tracked = rel in TRACKED
    untracked = rel in UNTRACKED
    ignored = rel in IGNORED
    return tracked, untracked, ignored


def _check_ignore_rule(path: Path) -> str:
    try:
        output = subprocess.check_output(
            ["git", "check-ignore", "-v", str(path.relative_to(ROOT).as_posix())],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        return ""
    return output


def _format_size_mb(size_bytes: int) -> float:
    return round(size_bytes / (1024 * 1024), 4)


def _iter_files(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_file():
            yield path
            continue
        if path.is_dir():
            for child in path.rglob("*"):
                if child.is_file():
                    yield child


def _file_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix in {".json", ".yaml", ".yml"}:
        return "config_or_artifact"
    if suffix in {".py", ".ps1", ".bat", ".sh"}:
        return "script_or_code"
    if suffix in {".md", ".txt"}:
        return "documentation"
    if suffix in {".tsx", ".ts", ".js", ".jsx"}:
        return "frontend_code"
    return suffix.lstrip(".") or "file"


def _purpose_for_path(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    if rel == ".env.example":
        return "safe example environment template"
    if rel == "structural_compounding_lab/shadow_forward" or rel.startswith("structural_compounding_lab/shadow_forward/"):
        return "research-only shadow-forward runtime and automation"
    if rel == "structural_compounding_lab/config" or rel.startswith("structural_compounding_lab/config/"):
        return "structural lab configuration"
    if rel == "structural_compounding_lab/docs" or rel.startswith("structural_compounding_lab/docs/"):
        return "structural lab runbook and operator docs"
    if rel == "structural_compounding_lab/tests" or rel.startswith("structural_compounding_lab/tests/"):
        return "structural lab regression coverage"
    if rel == "scripts" or rel.startswith("scripts/"):
        return "operator helper scripts"
    if rel == "structural_compounding_lab/output" or rel.startswith("structural_compounding_lab/output/"):
        return "generated research or shadow artifacts"
    if rel == "structural_compounding_lab/data_storage" or rel.startswith("structural_compounding_lab/data_storage/"):
        return "canonical structural lab local data"
    if rel == "data_storage" or rel.startswith("data_storage/"):
        return "root historical market data archive"
    if rel.endswith(".env") or rel.startswith(".env"):
        return "environment or secret material"
    if rel == "dashboard" or rel.startswith("dashboard/") or rel == "dashboard_api" or rel.startswith("dashboard_api/"):
        return "cockpit frontend/backend surface"
    if rel == "common" or rel.startswith("common/"):
        return "shared runtime and utility code"
    if rel == "backtest" or rel.startswith("backtest/"):
        return "retail trading system historical engine and diagnostics"
    if rel == "capital" or rel.startswith("capital/"):
        return "capital-routing research and allocator scaffolding"
    return "project asset"


def _project_role(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    if rel == ".env.example":
        return "REUSABLE_UTILITY"
    if rel == "structural_compounding_lab/shadow_forward" or rel.startswith("structural_compounding_lab/shadow_forward/"):
        return "ACTIVE_SHADOW_VALIDATION"
    if rel == "structural_compounding_lab/diagnostics" or rel.startswith("structural_compounding_lab/diagnostics/"):
        return "ACTIVE_CURRENT_EDGE"
    if rel == "structural_compounding_lab/tests" or rel.startswith("structural_compounding_lab/tests/"):
        return "ACTIVE_CURRENT_EDGE"
    if rel == "structural_compounding_lab/config" or rel.startswith("structural_compounding_lab/config/"):
        return "ACTIVE_CURRENT_EDGE"
    if rel == "structural_compounding_lab/docs" or rel.startswith("structural_compounding_lab/docs/"):
        return "ACTIVE_CURRENT_EDGE"
    if rel == "dashboard" or rel.startswith("dashboard/") or rel == "dashboard_api" or rel.startswith("dashboard_api/"):
        return "REUSABLE_FRONTEND_OR_UI"
    if rel == "common" or rel.startswith("common/") or rel == "scripts" or rel.startswith("scripts/"):
        return "REUSABLE_UTILITY"
    if (
        rel == "backtest"
        or rel.startswith("backtest/")
        or rel == "capital"
        or rel.startswith("capital/")
        or rel == "entry"
        or rel.startswith("entry/")
        or rel == "exit"
        or rel.startswith("exit/")
        or rel == "features"
        or rel.startswith("features/")
        or rel == "position"
        or rel.startswith("position/")
        or rel == "pyramiding"
        or rel.startswith("pyramiding/")
        or rel == "regime"
        or rel.startswith("regime/")
        or rel == "simulation"
        or rel.startswith("simulation/")
        or rel == "sniffing"
        or rel.startswith("sniffing/")
        or rel == "data"
        or rel.startswith("data/")
    ):
        return "ARCHIVED_BUT_PRESERVE"
    if (
        rel == "data_storage"
        or rel.startswith("data_storage/")
        or rel.startswith("live_sim/output/")
        or rel.startswith("backtest/output/")
        or rel == "structural_compounding_lab/output"
        or rel.startswith("structural_compounding_lab/output/")
        or rel == "structural_compounding_lab/data_storage"
        or rel.startswith("structural_compounding_lab/data_storage/")
    ):
        return "CACHE_OR_BUILD_ARTIFACT"
    if rel.endswith(".env") or rel.startswith(".env"):
        return "SECRET_OR_DO_NOT_COMMIT"
    return "REVIEW_MANUALLY"


def _recommended_action(path: Path) -> tuple[str, bool, bool, str, str]:
    rel = path.relative_to(ROOT).as_posix()
    tracked, untracked, ignored = _git_state(path)
    if rel == ".env.example":
        return "COMMIT_NORMAL", True, False, "safe example environment file", ""
    if rel.endswith(".env") or rel.startswith(".env"):
        return "DO_NOT_COMMIT_SECRET", False, False, "contains environment or secret material", ""
    if "__pycache__" in rel or rel.endswith(".pyc") or ".pytest_cache" in rel:
        return "DO_NOT_COMMIT_CACHE", False, True, "cache or compiled artifact", ""
    if rel == "data_storage" or rel.startswith("data_storage/"):
        return "DO_NOT_COMMIT_REDOWNLOAD_ON_MAC", True, True, "large root market archive can be recreated from public klines", "python main_download.py --symbol BTCUSDT --interval 1m --start-date 2018-01-01 --end-date 2026-06-13"
    if rel == "structural_compounding_lab/data_storage":
        return "REVIEW_MANUALLY", True, True, "contains canonical tape plus backups; keep canonical if explicitly approved, rebuild otherwise", "python -m structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater --mode update_and_catchup"
    if rel.startswith("structural_compounding_lab/data_storage/"):
        if ".backup_" in rel:
            return "DO_NOT_COMMIT_REGENERATE_ON_MAC", False, True, "backup snapshots are redundant if the canonical tape is preserved or rebuilt", ""
        return "COMMIT_SMALL_ARTIFACT", True, True, "small canonical structural shadow-forward tape is useful to preserve if approved; can also be rebuilt", "python -m structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater --mode update_and_catchup"
    if rel == "structural_compounding_lab/output" or rel.startswith("structural_compounding_lab/output/"):
        return "DO_NOT_COMMIT_REGENERATE_ON_MAC", False, True, "generated output artifacts should be rebuilt or summarized on Mac", ""
    if rel.startswith("live_sim/output/") or rel.startswith("backtest/output/"):
        return "DO_NOT_COMMIT_REGENERATE_ON_MAC", False, True, "runtime or backtest outputs are regenerable", ""
    if rel.startswith("dashboard/node_modules/") or rel.startswith("dashboard/.next/"):
        return "DO_NOT_COMMIT_CACHE", False, True, "frontend build cache", ""
    if path.suffix.lower() in {".png"} and path.name.startswith("tmp_"):
        return "DO_NOT_COMMIT_CACHE", False, False, "temporary screenshot artifact", ""
    if rel == "scripts" or rel.startswith("scripts/"):
        return "COMMIT_NORMAL", True, False, "operator helpers belong in the migration commit", ""
    if tracked or rel.startswith("structural_compounding_lab/"):
        return "COMMIT_NORMAL", True, False, "source, docs, tests, or small research config", ""
    return "REVIEW_MANUALLY", True, False, "worktree contains mixed legacy and exploratory files", ""


@dataclass
class CsvScan:
    row_count: int | None
    header: list[str]
    timestamp_column: str
    first_timestamp: str
    last_timestamp: str


def _scan_csv(path: Path) -> CsvScan:
    timestamp_candidates = [
        "timestamp",
        "open_time",
        "datetime",
        "entry_timestamp",
        "exit_timestamp",
        "date",
    ]
    first_timestamp = ""
    last_timestamp = ""
    row_count = 0
    header: list[str] = []
    timestamp_column = ""
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return CsvScan(row_count=0, header=[], timestamp_column="", first_timestamp="", last_timestamp="")
        header_lower = [column.strip().lower() for column in header]
        for candidate in timestamp_candidates:
            if candidate in header_lower:
                timestamp_column = header[header_lower.index(candidate)]
                break
        if not timestamp_column and header:
            timestamp_column = header[0]
        ts_index = header.index(timestamp_column) if timestamp_column in header else 0
        for row in reader:
            if not row:
                continue
            row_count += 1
            if ts_index < len(row):
                value = row[ts_index].strip()
                if not first_timestamp and value:
                    first_timestamp = value
                if value:
                    last_timestamp = value
    return CsvScan(
        row_count=row_count,
        header=header,
        timestamp_column=timestamp_column,
        first_timestamp=first_timestamp,
        last_timestamp=last_timestamp,
    )


def _status_files() -> None:
    MIGRATION_AUDIT.mkdir(parents=True, exist_ok=True)
    _write_text(MIGRATION_AUDIT / "git_status_short.txt", _run("git", "status", "--short"))
    _write_text(MIGRATION_AUDIT / "tracked_files.txt", _run("git", "ls-files"))
    _write_text(MIGRATION_AUDIT / "untracked_files.txt", _run("git", "ls-files", "--others", "--exclude-standard"))
    _write_text(MIGRATION_AUDIT / "ignored_files.txt", _run("git", "ls-files", "--others", "-i", "--exclude-standard"))


def _gitignore_rules() -> None:
    important = [
        ROOT / ".env",
        ROOT / ".env.template",
        ROOT / ".env.example",
        ROOT / "data_storage",
        ROOT / "backtest" / "output",
        ROOT / "live_sim" / "output",
        ROOT / "dashboard" / "node_modules",
        ROOT / "dashboard" / ".next",
        ROOT / "structural_compounding_lab" / "output",
        ROOT / "structural_compounding_lab" / "data_storage",
    ]
    rows: list[dict[str, object]] = []
    for path in important:
        rows.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "exists": path.exists(),
                "ignored": bool(_check_ignore_rule(path)),
                "gitignore_rule": _check_ignore_rule(path),
                "notes": (
                    "ignored by git"
                    if _check_ignore_rule(path)
                    else "not ignored; if large or regenerable, preserve via rebuild plan instead of blind commit"
                ),
            }
        )
    _write_csv(MIGRATION_AUDIT / "gitignore_rules_explained.csv", rows)


def _large_files() -> None:
    rows: list[dict[str, object]] = []
    for file_path in ROOT.rglob("*"):
        if not file_path.is_file():
            continue
        size_bytes = file_path.stat().st_size
        if size_bytes < 25 * 1024 * 1024:
            continue
        tracked, untracked, ignored = _git_state(file_path)
        rows.append(
            {
                "path": file_path.relative_to(ROOT).as_posix(),
                "size_mb": _format_size_mb(size_bytes),
                "tracked_by_git": tracked,
                "untracked": untracked,
                "ignored_by_git": ignored,
                "threshold_bucket": (
                    ">250MB"
                    if size_bytes >= 250 * 1024 * 1024
                    else ">100MB"
                    if size_bytes >= 100 * 1024 * 1024
                    else ">50MB"
                    if size_bytes >= 50 * 1024 * 1024
                    else ">25MB"
                ),
                "recommended_action": _recommended_action(file_path)[0],
            }
        )
    rows.sort(key=lambda row: float(row["size_mb"]), reverse=True)
    _write_csv(MIGRATION_AUDIT / "large_files.csv", rows)


def _critical_state_manifest() -> None:
    important_paths = [
        ROOT / "structural_compounding_lab" / "shadow_forward",
        ROOT / "structural_compounding_lab" / "config",
        ROOT / "structural_compounding_lab" / "docs",
        ROOT / "structural_compounding_lab" / "tests",
        ROOT / "scripts",
        ROOT / "structural_compounding_lab" / "output",
        ROOT / "structural_compounding_lab" / "data_storage",
        ROOT / "data_storage",
        ROOT / ".env.example",
        ROOT / ".env.template",
        ROOT / "config" / "structural_compounding_lab_project.json",
        ROOT / "dashboard",
        ROOT / "dashboard_api",
        ROOT / "common",
        ROOT / "backtest",
        ROOT / "capital",
        ROOT / "entry",
        ROOT / "exit",
        ROOT / "features",
        ROOT / "position",
        ROOT / "pyramiding",
        ROOT / "regime",
        ROOT / "simulation",
        ROOT / "sniffing",
        ROOT / "tests",
    ]
    rows: list[dict[str, object]] = []
    for path in important_paths:
        tracked, untracked, ignored = _git_state(path) if path.is_file() else (False, False, bool(_check_ignore_rule(path)))
        size_bytes = path.stat().st_size if path.exists() and path.is_file() else 0
        action, required_on_mac, can_regenerate, reason, rebuild = _recommended_action(path)
        rows.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "tracked_by_git": tracked,
                "untracked": untracked,
                "ignored_by_git": ignored,
                "gitignore_rule_if_ignored": _check_ignore_rule(path),
                "file_size_mb": _format_size_mb(size_bytes),
                "file_type": "directory" if path.is_dir() else _file_type(path),
                "purpose": _purpose_for_path(path),
                "project_role_classification": _project_role(path),
                "required_on_mac": required_on_mac,
                "can_regenerate": can_regenerate,
                "can_redownload": "BTCUSDT" in path.as_posix() or path.as_posix().startswith("data_storage/"),
                "recommended_action": action,
                "reason": reason,
                "rebuild_command_or_notes": rebuild,
            }
        )
    _write_csv(MIGRATION_AUDIT / "critical_state_manifest.csv", rows)


def _btc_files() -> list[Path]:
    files: list[Path] = []
    for candidate_root in [
        ROOT / "data_storage" / "BTCUSDT" / "1m",
        ROOT / "structural_compounding_lab" / "data_storage" / "BTCUSDT" / "1m",
        ROOT / "structural_compounding_lab" / "output",
    ]:
        if not candidate_root.exists():
            continue
        for file_path in candidate_root.rglob("*BTCUSDT*csv"):
            if file_path.is_file():
                files.append(file_path)
        for file_path in candidate_root.rglob("*btcusdt*csv"):
            if file_path.is_file() and file_path not in files:
                files.append(file_path)
    unique: list[Path] = []
    seen: set[str] = set()
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        if rel in seen:
            continue
        seen.add(rel)
        unique.append(path)
    return sorted(unique)


def _recreate_command_for_btc(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    name = path.name
    if name == "btcusdt_1m_canonical_shadow_forward.csv":
        return "python -m structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater --mode update_and_catchup"
    if name == "btcusdt_6m_1m_2025-12-13_to_2026-06-13.csv":
        return "python main_download.py --symbol BTCUSDT --interval 1m --start-date 2025-12-13 --end-date 2026-06-13  # use the root data_storage output as observer source on Mac"
    if "live_runtime" in name:
        return "Recreated by runtime only if needed; do not bootstrap research state from live runtime tape."
    if rel.startswith("data_storage/BTCUSDT/1m/"):
        return "python main_download.py --symbol BTCUSDT --interval 1m --start-date 2018-01-01 --end-date 2026-06-13"
    return ""


def _btc_data_manifest() -> None:
    rows: list[dict[str, object]] = []
    for path in _btc_files():
        tracked, untracked, ignored = _git_state(path)
        scan = _scan_csv(path)
        action, _, _, reason, _ = _recommended_action(path)
        rows.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "tracked_by_git": tracked,
                "untracked": untracked,
                "ignored_by_git": ignored,
                "file_size_mb": _format_size_mb(path.stat().st_size),
                "row_count": scan.row_count,
                "first_timestamp": scan.first_timestamp,
                "last_timestamp": scan.last_timestamp,
                "timestamp_column": scan.timestamp_column,
                "schema_columns": "|".join(scan.header),
                "needed_for_rebuild": path.name == "btcusdt_1m_canonical_shadow_forward.csv" or path.name == "BTCUSDT_1m_2018-01-01_to_2026-06-13.csv",
                "can_redownload_from_public_klines": "corrupt" not in path.name.lower(),
                "recommended_action": action,
                "reason": reason,
                "recreate_command_on_mac": _recreate_command_for_btc(path),
            }
        )
    _write_csv(MIGRATION_AUDIT / "btcusdt_data_manifest.csv", rows)

    lines = [
        "# Recreate BTCUSDT Data On Mac",
        "",
        "The preferred migration path is **clone code from GitHub, then rebuild BTC data locally on the Mac**.",
        "",
        "## 1. Rebuild the root public archive",
        "",
        "```bash",
        "python main_download.py --symbol BTCUSDT --interval 1m --start-date 2018-01-01 --end-date 2026-06-13",
        "```",
        "",
        "Expected output:",
        "",
        "- `data_storage/BTCUSDT/1m/BTCUSDT_1m_2018-01-01_to_2026-06-13.csv`",
        "",
        "## 2. Rebuild or extend the canonical structural shadow-forward tape",
        "",
        "```bash",
        "python -m structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater --mode update_and_catchup",
        "```",
        "",
        "Expected canonical output:",
        "",
        "- `structural_compounding_lab/data_storage/BTCUSDT/1m/btcusdt_1m_canonical_shadow_forward.csv`",
        "",
        "## 3. Validation checks",
        "",
        "- first timestamp should start at the historical start expected by the audit chain",
        "- last timestamp should reach the latest safe closed minute available at run time",
        "- gap count must be `0` in the updater summary",
        "- duplicate count must be `0` in the updater summary",
        "- updater must report `public_fetch_source=binance_public_klines`",
        "- no account, broker, paper, or live order path is allowed",
        "",
        "## 4. Resume behavior later",
        "",
        "The canonical updater is append-only and resume-capable. Re-run:",
        "",
        "```bash",
        "python -m structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater --mode update_and_catchup",
        "```",
        "",
        "It should continue from the last canonical timestamp rather than rebuilding from zero.",
    ]
    _write_text(MIGRATION_AUDIT / "recreate_btcusdt_data_on_mac.md", "\n".join(lines) + "\n")


def _output_artifact_manifest() -> None:
    rows: list[dict[str, object]] = []
    for folder in sorted([path for path in STRUCTURAL_OUTPUT.iterdir() if path.is_dir()]):
        files = list(folder.rglob("*"))
        file_count = len([child for child in files if child.is_file()])
        total_size = sum(child.stat().st_size for child in files if child.is_file())
        required_for_code = folder.name in {
            "research_architecture_fixture_run",
            "research_architecture_smoke",
            "smoke_run",
        }
        rows.append(
            {
                "path": folder.relative_to(ROOT).as_posix(),
                "file_count": file_count,
                "size_mb": _format_size_mb(total_size),
                "required_for_code_to_run": required_for_code,
                "required_only_for_audit_history": not required_for_code,
                "can_regenerate": True,
                "recommended_action": "COMMIT_SMALL_ARTIFACT" if required_for_code and total_size < 5 * 1024 * 1024 else "DO_NOT_COMMIT_REGENERATE_ON_MAC",
                "reason": "fixture or smoke output" if required_for_code else "generated research-court artifact; preserve via rebuild chain or summary instead of blind commit",
            }
        )
    _write_csv(MIGRATION_AUDIT / "output_artifact_manifest.csv", rows)

    summary_lines = [
        "# Output Artifact Summary For Mac",
        "",
        "Most `structural_compounding_lab/output/*` directories are **generated courts**, not source code.",
        "",
        "Recommended rule:",
        "",
        "- keep the code, configs, docs, tests, and small helper scripts in Git",
        "- do not try to force every historical output directory through GitHub",
        "- rebuild the key courts on Mac using `migration_audit/artifact_rebuild_chain.csv` and verify against `migration_audit/expected_rebuild_verification_targets.json`",
        "- preserve only small smoke or fixture outputs if they are genuinely useful for tests or UI empty states",
        "",
        "This keeps the migration GitHub-safe and avoids committing large historical ledgers unnecessarily.",
    ]
    _write_text(MIGRATION_AUDIT / "output_artifact_summary_for_mac.md", "\n".join(summary_lines) + "\n")


def _windows_path_audit() -> None:
    patterns = ["C:\\\\", "C:/", "\\\\Users\\\\", "OneDrive", "v25946b", "/abs/c:"]
    rows: list[dict[str, object]] = []
    scan_roots = [
        ROOT / "structural_compounding_lab",
        ROOT / "common",
        ROOT / "config",
        ROOT / "scripts",
        ROOT / "tests",
        ROOT / "dashboard",
        ROOT / "dashboard_api",
        ROOT / "README.md",
        ROOT / "MIGRATION_PLAN.md",
        ROOT / "MIGRATION_TO_MACBOOK_PRO.md",
    ]
    for path in _iter_files(scan_roots):
        rel = path.relative_to(ROOT).as_posix()
        if any(part in rel for part in ["/output/", "/node_modules/", "/.next/", "__pycache__"]):
            continue
        if path.suffix.lower() not in {".py", ".md", ".json", ".yaml", ".yml", ".txt", ".tsx", ".ts", ".js"}:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for line_no, line in enumerate(lines, start=1):
            for pattern in patterns:
                if pattern in line:
                    runnable = "historical" if "/output/" in rel else "runnable_or_doc"
                    if rel == "config/structural_compounding_lab_project.json":
                        fix = "Use local repo fallback or set STRUCTURAL_COMPOUNDING_LAB_ROOT on Mac; do not rely on Windows external root."
                    elif rel == "common/structural_lab_locator.py":
                        fix = "Already has local/env fallback; keep and verify on Mac."
                    elif rel.startswith("tests/"):
                        fix = "Fixture path only; leave or normalize if test portability fails."
                    else:
                        fix = "Replace with pathlib/project-root-relative path if this file is actively executed on Mac."
                    rows.append(
                        {
                            "file": rel,
                            "line": line_no,
                            "matched_path_or_pattern": pattern,
                            "runnable_or_historical": runnable,
                            "recommended_fix": fix,
                            "fixed_yes_no": "yes" if rel == "common/structural_lab_locator.py" else "no",
                            "notes": line.strip()[:240],
                        }
                    )
    _write_csv(MIGRATION_AUDIT / "windows_path_audit.csv", rows)


def _artifact_rebuild_chain() -> None:
    rows = [
        {
            "step_number": 1,
            "stage_name": "Root BTCUSDT public archive",
            "module_or_script": "main_download.py",
            "command_to_run": "python main_download.py --symbol BTCUSDT --interval 1m --start-date 2018-01-01 --end-date 2026-06-13",
            "required_inputs": "public Binance klines only",
            "expected_outputs": "data_storage/BTCUSDT/1m/BTCUSDT_1m_2018-01-01_to_2026-06-13.csv",
            "expected_key_metrics_or_classification": "historical 1m archive recreated",
            "can_skip_if_artifact_exists": True,
            "validation_command": "python -m unittest structural_compounding_lab.tests.test_fresh_btcusdt_data_updater -v",
            "notes": "Do this before structural updater because the updater is not a from-zero bootstrapper.",
        },
        {
            "step_number": 2,
            "stage_name": "Trusted 1H baseline and execution-cost court",
            "module_or_script": "structural_compounding_lab.diagnostics.execution_cost_realism_and_trade_redundancy_audit",
            "command_to_run": "python -m structural_compounding_lab.diagnostics.execution_cost_realism_and_trade_redundancy_audit",
            "required_inputs": "trusted BTC structural replay lineage",
            "expected_outputs": "structural_compounding_lab/output/execution_cost_realism_and_trade_redundancy_audit_001/",
            "expected_key_metrics_or_classification": "baseline average 792824.56; median 786049.45; 1M-hit windows 12",
            "can_skip_if_artifact_exists": True,
            "validation_command": "Inspect diagnostics/execution_cost_band_results.csv row NORMAL_MIXED_MAKER_TAKER_COST",
            "notes": "This is the baseline anchor for later courts.",
        },
        {
            "step_number": 3,
            "stage_name": "12H native execution rejection court",
            "module_or_script": "structural_compounding_lab.diagnostics.native_12h_execution_sleeve_discovery_audit",
            "command_to_run": "python -m structural_compounding_lab.diagnostics.native_12h_execution_sleeve_discovery_audit",
            "required_inputs": "trusted baseline outputs",
            "expected_outputs": "structural_compounding_lab/output/native_12h_execution_sleeve_discovery_audit_001/",
            "expected_key_metrics_or_classification": "NATIVE_12H_EXECUTION_REJECTED with repaired baseline reconciliation pass",
            "can_skip_if_artifact_exists": True,
            "validation_command": "Read native_12h_execution_sleeve_discovery_summary.json",
            "notes": "Confirms 12H execution retired and baseline accounting repaired.",
        },
        {
            "step_number": 4,
            "stage_name": "1H + 6H context role reconciliation",
            "module_or_script": "structural_compounding_lab.diagnostics.htf_context_role_reconciliation_audit",
            "command_to_run": "python -m structural_compounding_lab.diagnostics.htf_context_role_reconciliation_audit",
            "required_inputs": "trusted baseline and repaired 12H context",
            "expected_outputs": "structural_compounding_lab/output/htf_context_role_reconciliation_audit_001/",
            "expected_key_metrics_or_classification": "SIX_H_CONTEXT_IMPROVES_1H_RESEARCH_ONLY; LIGHT_BOOST_6H_CONFLUENCE",
            "can_skip_if_artifact_exists": True,
            "validation_command": "Read htf_context_role_reconciliation_summary.json",
            "notes": "This is the accepted research-only 6H context court.",
        },
        {
            "step_number": 5,
            "stage_name": "Earned gear discovery",
            "module_or_script": "structural_compounding_lab.diagnostics.earned_gear_activation_discovery_audit",
            "command_to_run": "python -m structural_compounding_lab.diagnostics.earned_gear_activation_discovery_audit",
            "required_inputs": "trusted baseline plus prior gear context",
            "expected_outputs": "structural_compounding_lab/output/earned_gear_activation_discovery_audit_001/",
            "expected_key_metrics_or_classification": "EARNED_GEAR_DISCOVERY_IMPROVES_BUT_FRAGILE",
            "can_skip_if_artifact_exists": True,
            "validation_command": "Read earned_gear_activation_discovery_summary.json",
            "notes": "Aggressive gear remains research-only comparison, not deployable logic.",
        },
        {
            "step_number": 6,
            "stage_name": "6H native execution scout court",
            "module_or_script": "structural_compounding_lab.diagnostics.six_hour_native_execution_tide_context_audit",
            "command_to_run": "python -m structural_compounding_lab.diagnostics.six_hour_native_execution_tide_context_audit",
            "required_inputs": "trusted baseline, 6H context court, repaired 12H court",
            "expected_outputs": "structural_compounding_lab/output/six_hour_native_execution_tide_context_audit_001/",
            "expected_key_metrics_or_classification": "SIX_H_NATIVE_EXECUTION_WEAK",
            "can_skip_if_artifact_exists": True,
            "validation_command": "Read six_hour_native_execution_tide_context_summary.json",
            "notes": "Confirms 6H execution scout did not beat the trusted 1H engine.",
        },
        {
            "step_number": 7,
            "stage_name": "Shadow-forward validation specification",
            "module_or_script": "structural_compounding_lab.diagnostics.shadow_forward_validation_spec_audit",
            "command_to_run": "python -m structural_compounding_lab.diagnostics.shadow_forward_validation_spec_audit",
            "required_inputs": "trusted 1H baseline, 6H context, 6H execution rejection",
            "expected_outputs": "structural_compounding_lab/output/shadow_forward_validation_spec_audit_001/",
            "expected_key_metrics_or_classification": "SHADOW_SPEC_READY_WITH_6H_CONTEXT_RESEARCH_ONLY",
            "can_skip_if_artifact_exists": True,
            "validation_command": "Read shadow_forward_validation_spec_summary.json",
            "notes": "Defines the forward court before any paper discussion.",
        },
        {
            "step_number": 8,
            "stage_name": "Shadow observer",
            "module_or_script": "structural_compounding_lab.shadow_forward.shadow_forward_observer",
            "command_to_run": "python -m structural_compounding_lab.shadow_forward.shadow_forward_observer --mode dry_run_backfill --source-csv data_storage/BTCUSDT/1m/BTCUSDT_1m_2025-12-13_to_2026-06-13.csv",
            "required_inputs": "source BTC 1m CSV and prior spec artifacts",
            "expected_outputs": "structural_compounding_lab/output/shadow_forward_observer_001/",
            "expected_key_metrics_or_classification": "SHADOW_OBSERVER_READY_RESEARCH_ONLY",
            "can_skip_if_artifact_exists": True,
            "validation_command": "Read shadow_forward_observer_summary.json",
            "notes": "Use the 6m root archive slice rebuilt from public BTC data as the observer source on Mac.",
        },
        {
            "step_number": 9,
            "stage_name": "Watchtower append-only observation",
            "module_or_script": "structural_compounding_lab.shadow_forward.shadow_forward_watchtower",
            "command_to_run": "python -m structural_compounding_lab.shadow_forward.shadow_forward_watchtower --mode single_cycle --source-csv data_storage/BTCUSDT/1m/BTCUSDT_1m_2018-01-01_to_2026-06-13.csv",
            "required_inputs": "observer artifacts and BTC archive",
            "expected_outputs": "structural_compounding_lab/output/shadow_forward_watchtower_001/",
            "expected_key_metrics_or_classification": "WATCHTOWER_READY_BUT_WAITING_FOR_FORWARD_DAYS",
            "can_skip_if_artifact_exists": True,
            "validation_command": "python -m unittest structural_compounding_lab.tests.test_shadow_forward_watchtower -v",
            "notes": "Append-only forward court; no orders allowed.",
        },
        {
            "step_number": 10,
            "stage_name": "Fresh BTC updater",
            "module_or_script": "structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater",
            "command_to_run": "python -m structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater --mode update_and_catchup",
            "required_inputs": "canonical shadow-forward tape or root BTC archive",
            "expected_outputs": "structural_compounding_lab/output/fresh_btcusdt_data_updater_001/",
            "expected_key_metrics_or_classification": "FRESH_DATA_READY_NO_NEW_ROWS or clean append state",
            "can_skip_if_artifact_exists": True,
            "validation_command": "python -m unittest structural_compounding_lab.tests.test_fresh_btcusdt_data_updater -v",
            "notes": "Public klines only; no broker endpoint.",
        },
        {
            "step_number": 11,
            "stage_name": "Pilot automation",
            "module_or_script": "structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation",
            "command_to_run": "python -m structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation --mode self_check && python -m structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation --mode daily_status",
            "required_inputs": "watchtower and fresh updater artifacts",
            "expected_outputs": "structural_compounding_lab/output/shadow_forward_pilot_automation_001/",
            "expected_key_metrics_or_classification": "AUTOMATION_READY_FOR_MANUAL_APPROVAL",
            "can_skip_if_artifact_exists": True,
            "validation_command": "python -m unittest structural_compounding_lab.tests.test_shadow_forward_pilot_automation -v",
            "notes": "Scheduler install remains optional and should stay manual.",
        },
    ]
    _write_csv(MIGRATION_AUDIT / "artifact_rebuild_chain.csv", rows)


def _expected_targets() -> None:
    payload = {
        "trusted_1h_baseline_rolling_5y_average_eur": {"value": 792824.56, "tolerance": 0.5},
        "trusted_1h_baseline_rolling_5y_median_eur": {"value": 786049.45, "tolerance": 0.5},
        "trusted_1h_baseline_1m_hit_windows": {"value": 12, "tolerance": 0},
        "six_h_context_final_classification": "SIX_H_CONTEXT_IMPROVES_1H_RESEARCH_ONLY",
        "six_h_context_best_variant": "LIGHT_BOOST_6H_CONFLUENCE",
        "six_h_context_normal_cost_rolling_5y_average_eur": {"value": 881465.53, "tolerance": 0.5},
        "six_h_context_normal_cost_rolling_5y_median_eur": {"value": 878431.05, "tolerance": 0.5},
        "six_h_native_execution_final_classification": "SIX_H_NATIVE_EXECUTION_WEAK",
        "twelve_h_execution_status": "execution retired / diagnostic only",
        "daily_tide_status": "diagnostic only",
        "weekly_deep_current_status": "diagnostic only",
        "shadow_spec_final_classification": "SHADOW_SPEC_READY_WITH_6H_CONTEXT_RESEARCH_ONLY",
        "shadow_observer_final_classification": "SHADOW_OBSERVER_READY_RESEARCH_ONLY",
        "watchtower_final_classification": "WATCHTOWER_READY_BUT_WAITING_FOR_FORWARD_DAYS",
        "fresh_updater_status": "public Binance klines only / no order endpoint",
        "pilot_automation_final_classification": "AUTOMATION_READY_FOR_MANUAL_APPROVAL",
        "future_candidate_base_capital_eur": 25000,
        "projected_5y_equity_reference_eur": 1062500,
        "capital_anchor_diagnostic_only": True,
        "paper_validation_ready": False,
    }
    _write_json(MIGRATION_AUDIT / "expected_rebuild_verification_targets.json", payload)


def _git_commit_plan() -> None:
    lines = [
        "# Git Commit Plan",
        "",
        "Do **not** run any of these commands until manually approved.",
        "",
        "## Safe normal commit scope",
        "",
        "```bash",
        "git add README.md MIGRATION_TO_MACBOOK_PRO.md MIGRATION_PLAN.md migration_audit/",
        "git add scripts/ structural_compounding_lab/shadow_forward/ structural_compounding_lab/config/ structural_compounding_lab/docs/ structural_compounding_lab/tests/ structural_compounding_lab/diagnostics/",
        "git add common/structural_lab_locator.py common/dashboard_telemetry.py dashboard/app/page.tsx dashboard/components/dashboard-shell.tsx dashboard/components/structural-lab-shell.tsx tests/test_dashboard_telemetry.py tests/test_structural_compounding_dashboard.py",
        "```",
        "",
        "## Optional small artifact scope only if explicitly desired",
        "",
        "```bash",
        "git add -f structural_compounding_lab/data_storage/BTCUSDT/1m/btcusdt_1m_canonical_shadow_forward.csv",
        "```",
        "",
        "## Files and folders to avoid",
        "",
        "- `.env`, `.env.*`, any secret or credential material",
        "- `data_storage/` root historical archives unless Git LFS is explicitly approved",
        "- `structural_compounding_lab/output/**` generated courts unless a tiny fixture is intentionally selected",
        "- `backtest/output/**`, `live_sim/output/**`",
        "- `dashboard/node_modules/`, `dashboard/.next/`, `dashboard/tsconfig.tsbuildinfo`",
        "- `__pycache__/`, `.pytest_cache/`, `*.pyc`",
        "- `tmp_*.png`, `dom_dump.txt`",
        "- unrelated `*-TL0380786*` exploratory files until manually reviewed",
        "",
        "## Manual-review files",
        "",
        "- `capital/__init__.py`",
        "- `capital/capital_lanes.py`",
        "- `capital/capital_promotion_review.py`",
        "- `refactor.md`",
        "- any untracked `capital/`, `backtest/`, or `tests/` additions not strictly required for the intended migration commit",
        "",
        "## Git LFS recommendation",
        "",
        "- **Not required** for the preferred migration path because the large BTC archives can be redownloaded on the Mac.",
        "- Consider Git LFS only if you explicitly choose to preserve the root `data_storage/BTCUSDT/1m/*.csv` history through GitHub rather than rebuilding it.",
        "",
        "## Recommended commit message",
        "",
        "```text",
        "Document structural shadow migration and Mac rebuild plan",
        "```",
        "",
        "## Warning",
        "",
        "The worktree is noisy. Review `git status --short` carefully before staging. Preserve legacy Retail Trading System areas; do not delete or silently drop them.",
    ]
    _write_text(MIGRATION_AUDIT / "git_commit_plan.md", "\n".join(lines) + "\n")


def _macbook_bootstrap_checklist() -> None:
    lines = [
        "# MacBook Bootstrap Checklist",
        "",
        "- [ ] `git clone <repo-url>`",
        "- [ ] `cd Retail-Trading-System`",
        "- [ ] `python3 -m venv .venv`",
        "- [ ] `source .venv/bin/activate`",
        "- [ ] `python -m pip install --upgrade pip`",
        "- [ ] `python -m pip install -r requirements.txt`",
        "- [ ] inspect `MIGRATION_PLAN.md` before running rebuild commands",
        "- [ ] export `STRUCTURAL_COMPOUNDING_LAB_ROOT` only if using an external structural-lab root on Mac",
        "- [ ] run the BTC rebuild step",
        "- [ ] run the artifact rebuild chain in order",
        "- [ ] run `python -m unittest structural_compounding_lab.tests.test_fresh_btcusdt_data_updater -v`",
        "- [ ] run `python -m unittest structural_compounding_lab.tests.test_shadow_forward_watchtower -v`",
        "- [ ] run `python -m unittest structural_compounding_lab.tests.test_shadow_forward_pilot_automation -v`",
        "- [ ] run `python -m structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation --mode self_check`",
        "- [ ] run `python -m structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation --mode daily_status`",
        "- [ ] confirm no live, paper, order, or broker path exists",
    ]
    _write_text(MIGRATION_AUDIT / "macbook_bootstrap_checklist.md", "\n".join(lines) + "\n")


def _final_rebuild_checklist() -> None:
    lines = [
        "# Final Rebuild Verification Checklist",
        "",
        "- [ ] BTCUSDT canonical CSV exists",
        "- [ ] BTCUSDT canonical CSV schema is valid",
        "- [ ] gap count is zero",
        "- [ ] duplicate count is zero",
        "- [ ] trusted `1H` baseline artifacts exist",
        "- [ ] `6H` context reconciliation artifacts exist",
        "- [ ] `6H` native execution weak/rejected artifacts exist",
        "- [ ] shadow spec artifacts exist",
        "- [ ] shadow observer artifacts exist",
        "- [ ] watchtower artifacts exist",
        "- [ ] fresh updater artifacts exist",
        "- [ ] pilot automation artifacts exist",
        "- [ ] self-check passes",
        "- [ ] daily status runs",
        "- [ ] no live/paper/order/broker path exists",
        "- [ ] future capital anchor remains diagnostic only",
    ]
    _write_text(MIGRATION_AUDIT / "final_rebuild_verification_checklist.md", "\n".join(lines) + "\n")


def _migration_docs() -> None:
    migration_to_mac = f"""# MIGRATION TO MACBOOK PRO

## Executive Summary

GitHub migration is feasible, but **GitHub clone alone will not reproduce the entire current working folder** because large historical data and most generated research outputs are intentionally outside the preferred commit scope. The safe path is:

1. push source, tests, docs, configs, scripts, and migration docs
2. clone on Mac
3. rebuild the BTCUSDT historical archive from public Binance klines
4. rebuild the structural research courts in the documented order
5. verify the expected classifications and safety flags

## What Should Be Pushed

- source code under the active Structural Compounding Lab
- shadow-forward runtime, watchtower, updater, and pilot automation code
- tests, docs, configs, and helper scripts
- migration docs and audit manifests
- preserved legacy Retail Trading System code that is already tracked or intentionally reusable

## What Should Not Be Pushed

- secrets or `.env` material
- root `data_storage/` BTC history unless you explicitly decide to use Git LFS
- generated `structural_compounding_lab/output/*` courts unless a tiny deterministic fixture is intentionally selected
- caches, build outputs, screenshots, `__pycache__`, `.next`, `node_modules`

## Git LFS

Git LFS is **not required** for the preferred migration path because the large BTC history can be rebuilt on the Mac from public klines. Use Git LFS only if you deliberately want GitHub to carry the root BTC archive files.

## BTCUSDT Data Strategy

- root BTC historical archive: rebuild on Mac
- canonical structural shadow-forward tape: either preserve the small ~10 MB canonical CSV or rebuild it with the fresh updater after the root archive exists
- live runtime CSV: do not treat it as migration anchor material

Important `.gitignore` nuance:

- the broad `data_storage/` ignore rule currently also catches `structural_compounding_lab/data_storage/`
- that means the canonical structural BTC tape will **not** move through Git unless you explicitly force-add it
- default recommendation remains: rebuild it on Mac unless you deliberately approve carrying that small canonical CSV

## Shadow Validation State To Preserve

- trusted BTC `1H` baseline remains the best proven engine
- `6H` context is accepted as research-only context
- `6H` native execution remains weak/rejected
- `12H` execution remains retired
- shadow-forward spec is ready
- observer is ready
- watchtower is ready but still waiting for the full `90` forward days
- fresh updater and pilot automation are ready
- future `EUR 25,000` capital anchor remains diagnostic only

## Exact Mac Setup Flow

See `MIGRATION_PLAN.md` for the detailed rebuild chain.

Quick bootstrap:

```bash
git clone <repo-url>
cd Retail-Trading-System
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main_download.py --symbol BTCUSDT --interval 1m --start-date 2018-01-01 --end-date 2026-06-13
python main_download.py --symbol BTCUSDT --interval 1m --start-date 2025-12-13 --end-date 2026-06-13
python -m structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater --mode update_and_catchup
```

Then continue with the rebuild ladder in `migration_audit/artifact_rebuild_chain.csv`.

## Safety

- `research_only=true`
- `paper_allowed=false`
- `live_allowed=false`
- `real_money_allowed=false`
- `behavior_change_allowed=false`
- future capital anchor recorded for planning only
- no broker, order, paper, or live activation should occur during migration or rebuild
"""
    _write_text(ROOT / "MIGRATION_TO_MACBOOK_PRO.md", migration_to_mac + "\n")

    migration_plan = f"""# MIGRATION PLAN

## Purpose

This document is the exact rebuild map for restoring the project on a MacBook Pro after a safe GitHub-based migration from the Windows office laptop. It assumes code moves through Git, while large ignored data and regenerated courts are rebuilt locally on the Mac.

## What Moves Through GitHub

- source code
- tests
- docs
- configs
- helper scripts
- migration manifests
- any explicitly approved small deterministic artifacts

## What Intentionally Does Not Move Through GitHub

- secrets
- broad root historical market archives under `data_storage/`
- most generated research courts under `structural_compounding_lab/output/`
- runtime state and caches

## Preserved Retail Trading System Legacy Components

The broader Retail Trading System codebase is **preserved**, not discarded.

Preserved legacy/frontend/project areas found in this repo include:

- `dashboard/`
- `dashboard_api/`
- `common/`
- `backtest/`
- `capital/`
- `data/`
- `entry/`
- `exit/`
- `features/`
- `position/`
- `pyramiding/`
- `regime/`
- `simulation/`
- `sniffing/`
- `tests/`

Classification guidance:

- `ACTIVE_CURRENT_EDGE`: current Structural Compounding Lab diagnostics and research code
- `ACTIVE_SHADOW_VALIDATION`: shadow-forward observer, watchtower, updater, pilot automation
- `ARCHIVED_BUT_PRESERVE`: older Retail Trading System strategy/replay/capital surfaces that are not the current edge but may contain reusable architecture
- `REUSABLE_FRONTEND_OR_UI`: cockpit, dashboard, route shells, market panels, chart surfaces
- `REUSABLE_UTILITY`: shared helpers, locators, scripts, telemetry
- `CACHE_OR_BUILD_ARTIFACT`: generated outputs, caches, build folders
- `SECRET_OR_DO_NOT_COMMIT`: `.env` and credential-bearing files
- `REVIEW_MANUALLY`: noisy exploratory files and mixed worktree items

Do **not** delete preserved legacy folders on the Mac just because the current active edge moved into the Structural Compounding Lab.

## BTCUSDT 1m Rebuild

Canonical root archive rebuild:

```bash
python main_download.py --symbol BTCUSDT --interval 1m --start-date 2018-01-01 --end-date 2026-06-13
```

Canonical structural shadow-forward rebuild:

```bash
python -m structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater --mode update_and_catchup
```

Expected canonical CSV on Mac:

- `structural_compounding_lab/data_storage/BTCUSDT/1m/btcusdt_1m_canonical_shadow_forward.csv`

Important `.gitignore` nuance:

- the repo-wide `data_storage/` rule also ignores `structural_compounding_lab/data_storage/`
- if you ever choose to preserve the canonical shadow-forward tape in Git, it requires `git add -f`
- default recommendation is still to rebuild it safely on Mac

## Artifact Rebuild Order

Follow `migration_audit/artifact_rebuild_chain.csv` exactly.

High-level order:

1. root BTC public archive
2. trusted `1H` execution-cost baseline
3. repaired `12H` execution court
4. `1H + 6H` context reconciliation
5. earned-gear court
6. `6H` native execution scout court
7. shadow-forward validation spec
8. shadow observer
9. watchtower
10. fresh BTC updater
11. pilot automation

## Expected Verification Targets

See `migration_audit/expected_rebuild_verification_targets.json`.

Most important anchors:

- trusted BTC `1H` baseline rolling `5Y` average: `EUR 792,824.56`
- trusted BTC `1H` baseline rolling `5Y` median: `EUR 786,049.45`
- trusted BTC `1H` baseline `1M` hit windows: `12`
- `6H` context classification: `SIX_H_CONTEXT_IMPROVES_1H_RESEARCH_ONLY`
- `6H` native execution classification: `SIX_H_NATIVE_EXECUTION_WEAK`
- shadow spec classification: `SHADOW_SPEC_READY_WITH_6H_CONTEXT_RESEARCH_ONLY`
- observer classification: `SHADOW_OBSERVER_READY_RESEARCH_ONLY`
- watchtower classification: `WATCHTOWER_READY_BUT_WAITING_FOR_FORWARD_DAYS`
- pilot automation classification: `AUTOMATION_READY_FOR_MANUAL_APPROVAL`

## How To Know The Edge Is Restored

The trusted `1H` engine is restored when:

- the normal mixed maker/taker cost row reproduces the known baseline metrics
- the later courts load that same baseline cleanly
- `6H` context improves the mission research-only
- `6H` native execution still fails to beat the baseline
- the shadow-forward spec/observer/watchtower chain rebuilds without creating order paths

## What To Do If Something Is Missing

- missing BTC root archive: rebuild with `main_download.py`
- missing canonical shadow-forward CSV: run the fresh updater
- missing research-court directory: run the corresponding module from the rebuild chain
- unexpected classification drift: compare against `migration_audit/expected_rebuild_verification_targets.json` and inspect the relevant summary JSON before proceeding

## Files That Should Never Be Manually Edited

- generated summaries in `structural_compounding_lab/output/*`
- runtime heartbeat or readiness logs
- historical ledgers used as frozen reference artifacts

## Files That Should Never Be Committed Blindly

- `.env` and secret-bearing files
- root `data_storage/` large archives
- generated output courts
- caches and build outputs

## MacBook Pro Bootstrap From Clean Clone

```bash
git clone <repo-url>
cd Retail-Trading-System
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main_download.py --symbol BTCUSDT --interval 1m --start-date 2018-01-01 --end-date 2026-06-13
python main_download.py --symbol BTCUSDT --interval 1m --start-date 2025-12-13 --end-date 2026-06-13
python -m structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater --mode update_and_catchup
python -m structural_compounding_lab.diagnostics.execution_cost_realism_and_trade_redundancy_audit
python -m structural_compounding_lab.diagnostics.native_12h_execution_sleeve_discovery_audit
python -m structural_compounding_lab.diagnostics.htf_context_role_reconciliation_audit
python -m structural_compounding_lab.diagnostics.earned_gear_activation_discovery_audit
python -m structural_compounding_lab.diagnostics.six_hour_native_execution_tide_context_audit
python -m structural_compounding_lab.diagnostics.shadow_forward_validation_spec_audit
python -m structural_compounding_lab.shadow_forward.shadow_forward_observer --mode dry_run_backfill --source-csv data_storage/BTCUSDT/1m/BTCUSDT_1m_2025-12-13_to_2026-06-13.csv
python -m structural_compounding_lab.shadow_forward.shadow_forward_watchtower --mode single_cycle --source-csv data_storage/BTCUSDT/1m/BTCUSDT_1m_2018-01-01_to_2026-06-13.csv
python -m structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation --mode self_check
python -m structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation --mode daily_status
```

## Final Safety Truth

Migration and rebuild do **not** change:

- live behavior
- paper behavior
- runtime order routing
- production allocator defaults
- production risk/sizing/entry/exit rules
- future capital anchor diagnostic-only status
"""
    _write_text(ROOT / "MIGRATION_PLAN.md", migration_plan + "\n")


def _root_audit_summary() -> None:
    rows = []
    for path in [ROOT / "README.md", ROOT / "MIGRATION_TO_MACBOOK_PRO.md", ROOT / "MIGRATION_PLAN.md"]:
        rows.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "exists": path.exists(),
                "size_mb": _format_size_mb(path.stat().st_size) if path.exists() else 0.0,
            }
        )
    _write_csv(MIGRATION_AUDIT / "generated_migration_files.csv", rows)


def main() -> None:
    MIGRATION_AUDIT.mkdir(parents=True, exist_ok=True)
    _status_files()
    _gitignore_rules()
    _large_files()
    _critical_state_manifest()
    _btc_data_manifest()
    _output_artifact_manifest()
    _windows_path_audit()
    _artifact_rebuild_chain()
    _expected_targets()
    _git_commit_plan()
    _macbook_bootstrap_checklist()
    _final_rebuild_checklist()
    _migration_docs()
    _root_audit_summary()
    _write_json(
        MIGRATION_AUDIT / "generation_meta.json",
        {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "research_only": True,
            "paper_allowed": False,
            "live_allowed": False,
            "real_money_allowed": False,
            "behavior_change_allowed": False,
            "notes": [
                "Migration package generated from current worktree and artifact truth.",
                "Legacy Retail Trading System areas were preserved and classified rather than deleted.",
            ],
        },
    )


if __name__ == "__main__":
    main()
