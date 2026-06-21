# Outage / Resume / Catch-Up Operational Court Report

## Final classification

`OUTAGE_RECOVERY_READY_RESEARCH_ONLY`

The operator runtime passed all required local fault scenarios and a real
public-data catch-up plus immediate idempotent rerun. This classification does
not change the frozen strategy, does not grant paper readiness, and does not
create any execution permission.

## 1. What was implemented

- Added a dedicated research-only operator:
  `structural_compounding_lab/shadow_forward/forward_validation_runtime.py`
- Added durable canonical/decision/trade reconciliation.
- Added per-decision checkpoint persistence.
- Added deterministic decision and simulated-observation trade IDs.
- Added bounded public gap backfill before decision processing.
- Added honest GREEN/YELLOW/RED status reporting.
- Added `run_once`, `status`, and `audit_outage_recovery` CLI modes.
- Added a 17-case outage recovery audit.
- Added 12 resilience unit/integration tests.

## 2. What already existed

- Dynamic Mac project-root discovery.
- Public Binance `1m` kline fetching without private endpoints.
- Closed-hour safety boundaries and incomplete-candle rejection.
- Atomic canonical CSV writes and backup behavior.
- Observer `1H` decision and `6H` context generation.
- Watchtower append-only ledger de-duplication.
- Pilot self-check, stale-data, scheduler, and safety reporting.
- Frozen strategy and frozen-rule integrity evidence.

## 3. Checkpoint/resume behavior now available

The runtime writes:

`structural_compounding_lab/output/forward_validation_runtime/checkpoints/forward_runtime_checkpoint.json`

The canonical tape is persisted before decisions are processed. The checkpoint
is then rewritten after every successfully persisted `1H` decision and any
corresponding internal simulated-observation row.

Recovery rules:

- crash after append: canonical-ahead state is audited and decision processing resumes;
- crash after partial decisions: runtime resumes after the final persisted decision;
- missing checkpoint: state is reconstructed from durable ledgers and existing watchtower boundary;
- canonical ahead of checkpoint: missing decisions are processed chronologically;
- immediate rerun: deterministic IDs prevent duplicate decisions and simulated rows.

## 4. Runtime folder

`structural_compounding_lab/output/forward_validation_runtime/`

This folder is gitignored.

## 5. Checkpoint schema

The checkpoint contains:

- project and canonical paths;
- canonical first/last timestamp and row count;
- latest safe market timestamp;
- last fetch start/end;
- last processed `1H` and `6H` timestamps;
- processed decision and simulated-trade IDs;
- last successful run/status/error;
- canonical checksum;
- Git commit, config hash, and frozen strategy signature;
- all required research-only safety flags.

## 6. `latest_status.json` schema

The status includes all required timing, canonical row, fetch, append,
de-duplication, gap, catch-up, interruption, decision, simulated-ledger,
scheduler, self-check, and safety fields.

Latest real run:

- status: `YELLOW`
- reason: `scheduler_not_installed_but_runtime_healthy`
- canonical rows before/after: `273420 / 273540`
- rows fetched/appended: `120 / 120`
- gaps before/after: `0 / 0`
- latest canonical before: `2026-06-20T20:59:00`
- latest canonical after: `2026-06-20T22:59:00`
- latest safe timestamp: `2026-06-20T22:59:00`
- caught up to realtime: `true`
- decisions processed: `2`
- simulated trades created: `0`

Immediate rerun:

- rows fetched/appended: `0 / 0`
- decisions processed: `0`
- simulated trades created: `0`
- gaps: `0`
- same final decision checkpoint;
- status remained honestly YELLOW because the scheduler is not installed.

## 7. Outage cases tested

The audit tested:

1. clean normal run;
2. immediate rerun;
3. 30-minute outage;
4. 3-hour outage;
5. 24-hour outage;
6. multi-day outage;
7. crash after data append;
8. crash after partial decision processing;
9. duplicate candle input/fetch;
10. missing candle followed by bounded backfill;
11. public fetch timeout/failure;
12. canonical exists with checkpoint missing;
13. checkpoint state behind canonical;
14. duplicate canonical timestamps;
15. canonical gap;
16. timezone normalization;
17. scheduler missing while runtime is otherwise healthy.

The audit used a local slice of the rebuilt public canonical BTCUSDT tape, not
private, signed, account, order, broker, or synthetic strategy-validation data.

## 8. Cases passed

`17 / 17`

## 9. Cases failed

None.

## 10. Manual rerun idempotency

Passed. Immediate rerun created:

- zero duplicate candles;
- zero duplicate decisions;
- zero duplicate simulated trades;
- zero additional rows when no new market data existed.

## 11. Multi-hour/day catch-up

Passed for 30 minutes, 3 hours, 24 hours, and multiple days using bounded local
public-data fixtures. Missing rows were appended chronologically and gaps were
zero after recovery.

## 12. Crash after append

Passed. The canonical tape remained durable, and the next run resumed decision
processing from reconciled canonical/checkpoint state.

## 13. Crash after partial decision processing

Passed. The checkpoint persisted after each decision. The resumed run continued
after the final durable decision without duplicates.

## 14. Duplicate prevention

Decisions use deterministic observer signal IDs. Internal simulated-observation
rows use `SIM-<decision_id>`. Both ledgers are checked before append, and their
processed IDs are stored in the checkpoint.

## 15. Generated files and Git ignore

The following remain ignored:

- canonical and root `data_storage/`;
- `structural_compounding_lab/data_storage/`;
- `structural_compounding_lab/output/`;
- `.venv311/`;
- `.env`;
- runtime checkpoints, ledgers, statuses, and audit artifacts.

## 16. Test results

- Forward runtime resilience: `12/12`
- Fresh BTCUSDT updater: `6/6`
- Shadow-forward watchtower: `6/6`
- Shadow-forward pilot automation: `6/6`
- Shadow-forward observer: `3/3`
- Dashboard and telemetry: `15/15`

Total: `48/48` passed.

## 17. Safety flags

- `research_only=true`
- `real_money_allowed=false`
- `paper_allowed=false`
- `live_allowed=false`
- `behavior_change_allowed=false`
- `order_path_exists=false`
- `broker_path_exists=false`
- `paper_validation_ready=false`
- `eur_25000_anchor_active=false`

## 18. Paper/live/order/broker confirmation

No paper brokerage, live execution, exchange account, order, signed request, or
broker client was added or called. The simulated trade ledger is an internal
research observation artifact only.

## 19. EUR 25,000 confirmation

EUR 25,000 remains a diagnostic/planning anchor only. It is not active capital
and is not used for runtime sizing.

## 20. Interruption tolerance

The research-only six-month forward-validation operator can tolerate missed
runs, sleep/restart, short through multi-day data outages, append/processing
crashes, duplicate fetches, recoverable gaps, and manual reruns without data
loss or duplicate decisions.

## 21. Next recommended action

Keep the runtime research-only and collect forward operational evidence.
Optionally install a Mac-native scheduler only in a separately approved
operator task. Continue the 90-day shadow validation; do not enable paper or
live trading.

## Binance reconnect, self-healing, and critical email alerting

Classification:

`BINANCE_RECONNECT_ALERTING_READY_RESEARCH_ONLY`

### Retry policy

The public fetch layer uses finite quick, medium, and slow retry tiers:

- quick: 10, 20, and 30 seconds;
- medium: 60, 120, and 180 seconds;
- slow: 300 and 600 seconds.

Every attempt records its timestamp, requested range, delay, result, row count,
and sanitized failure type. Tests inject zero-delay timing. The runtime never
retries forever.

### Self-healing actions

The runtime:

- records internet, DNS, and Binance public-API checks;
- retries the exact public kline range;
- validates complete minute coverage and OHLC structure;
- rejects empty, malformed, partial, future, or incomplete responses;
- reduces failed large ranges into bounded smaller windows;
- re-fetches bounded canonical gaps;
- de-duplicates returned and local canonical timestamps;
- re-audits gaps before processing decisions;
- reconciles canonical/checkpoint divergence;
- reconstructs missing checkpoint state from canonical and durable ledgers;
- stops with RED on exhausted required catch-up or local durable-write failure.

### YELLOW and RED behavior

YELLOW is used when:

- a temporary fetch issue is recovered after retries;
- the scheduler is not installed;
- the runtime remains safe and data integrity is preserved.

RED is used when:

- required candles cannot be fetched after all retry tiers and reduced-window recovery;
- a gap or corruption remains;
- checkpoint reconciliation is unsafe;
- a canonical/checkpoint/decision write fails;
- any research-only safety invariant is violated.

### Critical email alert

Final RED status triggers one immediate critical alert addressed to:

`nneupane1@gmail.com`

Subject:

`[Retail Trading System] CRITICAL: Forward validation recovery failed`

The body includes the run, project root, Git commit, exact reason, failed
component, retry timeline, canonical and safe timestamps, missing range,
fetch/append counts, gap/duplicate state, decision checkpoint, safety flags,
and actionable operator steps.

### SMTP and local draft behavior

SMTP is configured only through untracked environment variables:

- `RTS_ALERT_EMAIL_ENABLED`
- `RTS_ALERT_EMAIL_TO`
- `RTS_ALERT_EMAIL_FROM`
- `RTS_ALERT_SMTP_HOST`
- `RTS_ALERT_SMTP_PORT`
- `RTS_ALERT_SMTP_USERNAME`
- `RTS_ALERT_SMTP_PASSWORD`
- `RTS_ALERT_EMAIL_DRY_RUN`
- `RTS_ALERT_EMAIL_COOLDOWN_HOURS`

No SMTP password or credential is hardcoded, logged, or written to reports.
If SMTP is absent, disabled, fails, or is in dry-run mode, the alert is written
to:

`structural_compounding_lab/output/forward_validation_runtime/alerts/latest_failure_email_draft.txt`

The runtime does not crash merely because SMTP is unavailable.

### Alert throttling

Alert state is stored at:

`structural_compounding_lab/output/forward_validation_runtime/alerts/alert_state.json`

The same failure signature is suppressed for six hours by default. A changed
failure reason may alert immediately. Recovery email is not sent by default.

### Status additions

`latest_status.json` now includes:

- retry attempt count and policy;
- sanitized fetch failure type and retry timeline;
- recovery actions attempted/succeeded/failed;
- final failure signature;
- email required/sent/draft fields;
- alert path and throttle status/reason.

### Safety confirmation

- `research_only=true`
- `real_money_allowed=false`
- `paper_allowed=false`
- `live_allowed=false`
- `behavior_change_allowed=false`
- `order_path_exists=false`
- `broker_path_exists=false`
- `paper_validation_ready=false`
- `eur_25000_anchor_active=false`

The reconnect and alerting layer does not change thresholds, entries, exits,
sizing, `6H` context, paper/live permissions, broker behavior, or order paths.
EUR 25,000 remains diagnostic-only.
