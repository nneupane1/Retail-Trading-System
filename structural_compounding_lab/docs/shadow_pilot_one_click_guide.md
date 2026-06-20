# Shadow Pilot One-Click Guide

## What it does

Runs a research-only hourly pilot cycle: fetch fresh public BTCUSDT 1m data, append the canonical local tape, process closed 1H candles, annotate 6H context, update the watchtower, write heartbeat/readiness, and stop.

## What it never does

- no orders
- no paper trading
- no live trading
- no broker execution
- no 25,000 EUR sizing

## Commands

```powershell
python -m structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation --mode self_check
python -m structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation --mode manual_test_run
python -m structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation --mode generate_scheduler_command
python -m structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation --mode install_scheduler_task --confirm-install-scheduler
python -m structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation --mode daily_status
python -m structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation --mode remove_scheduler_task --confirm-remove-scheduler
```

## Workflow

1. Run self-check.
2. Run one manual test.
3. Generate the scheduler command.
4. Install the scheduler only after explicit confirmation.
5. Check the daily status report once per day.

## Meanings

- GREEN: continue
- YELLOW: inspect warning
- RED: stop and fix before continuing

## Operational note

If the laptop sleeps, the hourly pilot will miss cycles. A VPS or always-awake machine is better for the 90-day court.

Paper validation remains blocked until the shadow-forward gates pass.
