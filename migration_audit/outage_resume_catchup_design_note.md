# Outage / Resume / Catch-Up Design Note

## 1. What already works today?

- Mac project-root discovery is dynamic through
  `structural_compounding_lab.common.project_paths`.
- The fresh BTCUSDT updater resolves the canonical tape below the clone root,
  computes the latest fully closed hourly boundary, fetches public Binance
  `1m` klines, rejects incomplete/future rows, de-duplicates timestamps,
  performs OHLC/gap checks, and writes the canonical CSV atomically.
- The shadow observer resamples `1H` and `6H`, calls the existing frozen
  decision components, produces deterministic signal IDs, and supports a
  last-processed-candle checkpoint.
- The watchtower appends observer rows with deterministic key-based
  de-duplication and preserves research-only safety flags.
- Pilot automation reports stale data, gaps, safety failures, scheduler state,
  and keeps `paper_validation_ready=false`.
- The last-six-month court proved the frozen engine on the rebuilt canonical
  data without changing strategy behavior.

## 2. What checkpoint/state files already exist?

- Fresh updater:
  `structural_compounding_lab/output/fresh_btcusdt_data_updater_001/_checkpoints/fresh_data_updater.checkpoint.json`
- Observer:
  `structural_compounding_lab/output/shadow_forward_observer_001/_checkpoints/shadow_forward_observer.checkpoint.json`
- Watchtower:
  `structural_compounding_lab/output/shadow_forward_watchtower_001/_checkpoints/watchtower_ingest_checkpoint.json`
- Pilot automation:
  `structural_compounding_lab/output/shadow_forward_pilot_automation_001/_checkpoints/pilot_automation_checkpoint.json`

These checkpoints are useful within their individual modules, but none is the
single durable transaction record covering canonical append, decision
processing, simulated-ledger append, and restart reconciliation.

## 3. What is missing for outage-safe six-month forward validation?

- One runtime-owned checkpoint that reconciles canonical state and decision
  state after sleep, restart, fetch failure, or partial processing.
- Explicit recovery when the canonical CSV is ahead of the checkpoint.
- A checkpoint write after every successfully persisted `1H` decision.
- A deterministic research-only simulated-ledger ID and de-duplication rule.
- Bounded gap backfill before decisions are processed.
- Honest GREEN/YELLOW/RED status for fetch failure, unresolved gaps,
  corruption, scheduler absence, and successful idempotent reruns.
- Automated fault-injection tests for crash-after-append and
  crash-after-partial-decision scenarios.

## 4. Which module should own checkpoint/resume behavior?

A dedicated
`structural_compounding_lab.shadow_forward.forward_validation_runtime`
orchestrator should own the durable runtime checkpoint. It will not own
strategy logic. It will reconcile the canonical tape, runtime ledgers, and
checkpoint at startup, then persist a checkpoint after every decision row.

## 5. Which module should own public data catch-up?

The fresh BTCUSDT updater remains the source of public Binance fetch,
closed-candle normalization, canonical quality, and atomic-write behavior.
The runtime orchestrator will reuse those helpers and add bounded missing-range
backfill plus outage-level status reporting.

## 6. Which module should own decision de-duplication?

The new runtime orchestrator should own de-duplication for its own durable
forward ledgers. Decision IDs remain the observer's deterministic
`BTCUSDT-<1H timestamp>` IDs. Simulated ledger IDs will be deterministic from
the decision ID. Existing observer/watchtower behavior remains unchanged.

## 7. Which tests will prove idempotency?

Local fixture and mocked-fetch tests will cover:

- short, multi-hour, 24-hour, and multi-day catch-up;
- immediate rerun with no duplicate candles, decisions, or simulated rows;
- crash after canonical append and resume from canonical-ahead state;
- crash after a partial decision batch and resume from the last checkpoint;
- incomplete current candle rejection;
- bounded gap backfill before decision processing;
- missing-checkpoint reconstruction;
- canonical-ahead-of-checkpoint reconciliation;
- duplicate candle removal;
- timezone normalization;
- public-fetch failure classification;
- scheduler-missing YELLOW classification;
- invariant research-only safety flags and absence of order/broker paths.

## 8. How will paper/live/order/broker behavior be avoided?

- The runtime imports no broker, account, order, paper-execution, or
  live-execution client.
- Data fetch uses only the existing public Binance klines helper.
- The simulated ledger is an internal research artifact containing
  deterministic observation rows only; it sends nothing externally.
- Safety flags are written into every checkpoint and status file with:
  `research_only=true`, all execution permissions false,
  `paper_validation_ready=false`, no order/broker path, and the EUR 25,000
  anchor inactive.
- Frozen strategy source/config hashes are recorded and checked. No thresholds,
  entries, exits, sizing, or `6H` context behavior are changed.
