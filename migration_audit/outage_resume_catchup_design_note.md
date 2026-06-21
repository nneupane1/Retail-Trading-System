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

## Binance reconnect, self-healing, and critical failure email alerting design

### 1. What fetch failures can happen?

The operator can encounter offline networking, DNS resolution failure,
connection/read timeout, HTTP `429`, HTTP `418`, Binance `5xx`, malformed or
empty JSON, partial candle ranges, duplicate candles, unresolved gaps, local
file locks, permission failures, and exhausted disk space.

### 2. Which failures are recoverable?

Temporary network/DNS/timeouts, rate limits, `418`, `5xx`, malformed/empty
responses, partial large requests, duplicate responses, and bounded gaps are
recoverable when a later retry or reduced-window fetch returns a complete,
valid range. Duplicate local rows are recoverable through de-duplication and
an atomic clean rewrite. Canonical-ahead and missing-checkpoint states are
recoverable from the canonical tape and durable ledgers.

### 3. Which failures are fatal after retries?

Failure is RED after bounded retries when required missing candles still cannot
be fetched, a gap remains, canonical OHLC data remains corrupt, checkpoint
state cannot be reconciled, a disk/permission/file-lock error prevents durable
write, or any research-only safety invariant is violated.

### 4. What retry/backoff policy is used?

The default bounded policy is:

- quick: 3 attempts with 10, 20, and 30 second delays;
- medium: 3 attempts with 60, 120, and 180 second delays;
- slow: 2 attempts with 300 and 600 second delays.

Tests inject zero-delay timing. The policy is finite and every attempt is
recorded. A failed large range is retried in smaller bounded chunks before the
runtime declares final failure.

### 5. What self-healing actions are attempted?

The runtime records network/DNS/Binance checks, retries public klines, reduces
the request window, re-fetches exact missing ranges, validates timestamp and
OHLC coverage, de-duplicates, re-audits gaps, cleans duplicate canonical rows,
reconciles checkpoint/canonical divergence, rebuilds a missing checkpoint from
durable state, and stops safely on local write or disk failure.

### 6. What makes status GREEN/YELLOW/RED?

- GREEN: current, clean, safely processed, scheduler installed, no recovery
  warnings.
- YELLOW: a temporary issue recovered, scheduler is absent, or the tape is
  temporarily stale without corruption and without exhausted required
  catch-up.
- RED: retries exhausted with required data missing, unresolved gap/corruption,
  unrecoverable checkpoint or disk write failure, or any safety violation.

### 7. When is email alerting triggered?

One critical alert is sent or drafted only after final RED classification and
all bounded recovery attempts are exhausted. The recipient defaults to
`nneupane1@gmail.com`.

### 8. How is email alert spam prevented?

`alerts/alert_state.json` stores the last failure signature and alert time.
The same unresolved failure is suppressed for a configurable cooldown,
defaulting to six hours. A changed failure signature may alert immediately.

### 9. How are secrets avoided?

SMTP configuration is read only from `RTS_ALERT_*` environment variables.
No password, token, API key, SMTP credential, or `.env` content is written to
status, diagnostics, reports, drafts, or logs. If SMTP is unavailable, the
operator writes a local gitignored email draft and does not crash.

### 10. How is research-only safety preserved?

The reconnect and alerting layer changes only operational transport,
durability, and notification behavior. It does not import or create trading,
broker, account, order, paper, or live execution paths. All safety flags remain
false except `research_only=true`, and EUR 25,000 remains inactive diagnostic
context.
