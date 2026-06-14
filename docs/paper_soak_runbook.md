# Paper Soak Runbook

## Purpose

This runbook governs the forward paper-soak phase for the routed multi-sleeve system.

The system is currently classified as `paper-only`.

Required constraints during soak:

- no real money
- no strategy tuning
- no threshold tuning
- no universe expansion
- no new sleeves
- no optimizer changes
- no capital-expression refactor

These remain forbidden until enough forward paper evidence exists and a later promotion review explicitly says otherwise.

## Start Paper Runtime

Run the single-entry launcher from the repository root:

```powershell
python run_live_cockpit.py
```

Expected truth after startup:

- dashboard opens in the browser
- `classification=paper-only`
- `paper_runtime_allowed=true`
- `real_money_allowed=false`
- `ssl_verify=true`
- validated boundary is displayed
- paper runtime artifacts appear under `live_sim/output`

## Stop Safely

If the launcher is running in the terminal, stop it with `Ctrl+C`.

Expected safe-stop behavior:

- runtime exits without switching to real money
- latest portfolio snapshot remains in `live_sim/output/portfolio_runtime_state.json`
- soak artifacts remain available for inspection

## Restart

Restart with the same command:

```powershell
python run_live_cockpit.py
```

After restart, verify:

- `live_sim/output/paper_runtime_events.jsonl` has a new startup record
- `live_sim/output/paper_runtime_startup_report.json` updates
- `live_sim/output/paper_soak_status.json` updates
- `live_sim/output/paper_soak_daily_report.json` updates
- restored state path, restored position count, and runtime timestamps are displayed in the dashboard

## Artifacts To Check

Primary runtime artifacts:

- `live_sim/output/paper_soak_status.json`
- `live_sim/output/paper_soak_daily_report.json`
- `live_sim/output/paper_runtime_events.jsonl`
- `live_sim/output/paper_runtime_startup_report.json`
- `live_sim/output/portfolio_runtime_state.json`
- `live_sim/output/portfolio_status.json`
- `live_sim/output/engine_heartbeat.json`

Validation and readiness artifacts:

- `backtest/output/production_validation_gate_current/summary.json`
- `backtest/output/production_validation_gate_current/promotion_readiness_report.json`

## Verify No Backtest Trades Were Imported

Use these checks:

- `paper_runtime_startup_report.json` must show restore state coming from `live_sim/output/portfolio_runtime_state.json`
- no path under `backtest/output` should be used as restored live state
- open paper positions count should reflect genuine paper runtime state only
- validation and holdout trades must never appear as restored live open positions

## Verify Heartbeat Health

Check:

- `paper_soak_status.json`
- `paper_soak_daily_report.json`
- dashboard runtime sections

Healthy signs:

- `last_heartbeat_timestamp` is current
- `runtime_last_processed_timestamp` advances with fresh closed candles
- no stale heartbeat warning
- no stale artifact warning

## Verify Dashboard Truth

The dashboard is read-only.

It must reflect artifact truth for:

- readiness classification
- validated boundary
- runtime last processed timestamp
- paper equity
- open positions
- active sleeves
- disabled sleeves
- daily paper soak report
- artifact freshness
- promotion status

If dashboard values disagree with the JSON artifacts, trust the JSON artifacts first and treat the dashboard as stale until refreshed.

## Warning Meanings

Common warnings:

- `classification_paper_only`: system remains in forward-paper evidence mode
- `real_money_blocked`: real-money startup must remain fail-closed
- `holdout_edge_thin`: holdout passed, but recent edge was thin and still needs forward proof
- `dashboard_detected_stale_heartbeat:*`: runtime may be stalled or not processing fresh candles
- `dashboard_detected_stale_artifacts:*`: runtime artifacts are not being refreshed
- `missing_artifact:*`: required runtime or validation artifact is missing
- `stale_artifact:*`: artifact exists but has not been updated recently

## What Must Remain Forbidden During Soak

During the soak window, do not:

- enable real money
- change sleeves
- change symbols
- change allocator rules
- change thresholds
- change strategy logic
- change risk expression
- rerun optimization

The goal of soak is evidence collection, restart safety, runtime observability, and operator discipline, not research iteration.
