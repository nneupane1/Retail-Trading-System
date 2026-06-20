# Shadow-Forward Watchtower Runbook

## What it is

The shadow-forward watchtower is a research-only operational wrapper around the validated shadow observer. It watches the 1H structural signal engine, appends evidence ledgers, tracks readiness, and generates operator reports.

## What it does

- Runs the observer in a safe single-cycle mode.
- Appends 1H signal, 6H context, research overlay, data-quality, and run logs.
- Writes heartbeat, readiness, safety, and operational-risk diagnostics.
- Generates daily, weekly, and cumulative read-only reports.

## What it never does

- It never places orders.
- It never creates paper trades.
- It never creates live trades.
- It never talks to broker account or order endpoints.
- It never changes allocator, risk, sizing, entries, exits, thresholds, sleeves, or production config defaults.

## Commands

```powershell
python -m structural_compounding_lab.shadow_forward.shadow_forward_watchtower --mode self_check
python -m structural_compounding_lab.shadow_forward.shadow_forward_watchtower --mode single_cycle
python -m structural_compounding_lab.shadow_forward.shadow_forward_watchtower --mode daily_report
python -m structural_compounding_lab.shadow_forward.shadow_forward_watchtower --mode weekly_report
python -m structural_compounding_lab.shadow_forward.shadow_forward_watchtower --mode status
```

## How to run one cycle

1. Run `self_check`.
2. Confirm `safety_guard_report.json` says `passed: true`.
3. Run `single_cycle`.
4. Inspect:
   - `diagnostics/heartbeat.json`
   - `diagnostics/readiness_progress.json`
   - `ledger/watchtower_run_log.csv`

## How to stop safely

The watchtower is single-cycle by default. Let the process exit naturally after it writes status, summary, and report artifacts.

## How to resume

Rerun the same command. The observer workspace and append-only watchtower ledgers will resume safely and skip already-ingested 1H candles.

## How to inspect ledgers

- `ledger/watchtower_signal_log.csv`
- `ledger/watchtower_context_log.csv`
- `ledger/watchtower_research_overlay_log.csv`
- `ledger/watchtower_data_quality_log.csv`
- `ledger/watchtower_run_log.csv`

## How to spot stale data

- Check `diagnostics/heartbeat.json` for `last_processed_1h_candle` and `warnings`.
- Check `diagnostics/operational_risk_status.json` for stale-runtime warnings.

## How to know paper validation is still blocked

`diagnostics/readiness_progress.json` keeps `paper_validation_ready=false` until all shadow-forward gates are satisfied from real forward observation.

## What not to touch

- Do not bypass the safety guard.
- Do not point the watchtower at private broker credentials.
- Do not change the observer into paper or live mode.
- Do not connect the 25k future capital anchor to sizing or execution.

## Emergency rule

If `safety_guard_report.json` says the guard failed, do not bypass it. Fix the cause and rerun `self_check`.
