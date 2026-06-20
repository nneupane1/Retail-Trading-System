# MIGRATION PLAN

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
