# Windows Task Scheduler Notes for Shadow Watchtower

## Purpose

These notes document how to schedule the research-only watchtower. This does not create paper trading, live trading, or broker execution.

## Recommended timing

Run a few minutes after each 1H candle close. Example: `HH:03` UTC-aligned equivalent on the local machine.

## Example action

Program/script:

```text
python
```

Arguments:

```text
-m structural_compounding_lab.shadow_forward.shadow_forward_watchtower --mode single_cycle
```

Start in:

```text
C:\Users\v25946b\OneDrive - Iveco Group\Documents\Retail-Trading-System
```

## Python / venv path

Use the same Python interpreter that already runs the structural lab tests successfully.

## Logging stdout/stderr

If needed, wrap the command in a `.bat` file and redirect stdout/stderr to a local log file.

## Disable the task

Disable the task from Task Scheduler if the safety guard fails or if the market-data source becomes stale.

## Verify no-order path before scheduling

Run this first:

```powershell
python -m structural_compounding_lab.shadow_forward.shadow_forward_watchtower --mode self_check
```

Confirm:

- `diagnostics/safety_guard_report.json` has `passed: true`
- `allow_order_endpoints: false`
- `allow_private_api_keys: false`
- `paper_allowed: false`
- `live_allowed: false`
- `real_money_allowed: false`
