# Manual Promotion Review

## Purpose

This document defines the human review process that sits on top of the forward paper-soak artifacts.

It does not enable real money.
It does not change trading logic.
It does not authorize a capital-expression refactor.

Current hard constraints:

- `classification=paper-only`
- `paper_runtime_allowed=true`
- `real_money_allowed=false`
- `ssl_verify=true`
- `validated_boundary=2026-06-13T00:00:00+00:00`

## Required Artifacts

Paper runtime artifacts:

- `live_sim/output/paper_runtime_startup_report.json`
- `live_sim/output/paper_runtime_events.jsonl`
- `live_sim/output/paper_soak_status.json`
- `live_sim/output/paper_soak_daily_report.json`
- `live_sim/output/paper_soak_review.json`
- `live_sim/output/paper_soak_review_history.jsonl`
- `live_sim/output/baseline_freeze_snapshot.json`
- `live_sim/output/portfolio_runtime_state.json`
- `live_sim/output/portfolio_status.json`
- `live_sim/output/engine_heartbeat.json`

Validation artifacts:

- `backtest/output/production_validation_gate_current/summary.json`
- `backtest/output/production_validation_gate_current/promotion_readiness_report.json`

## Minimum Soak Duration

Read the configured threshold from:

- `config/settings.json`
- `paper_soak.minimum_days_before_review`

Current default is conservative:

- `14` days

If `paper_soak_review.json` shows fewer completed days than required, the only acceptable outcome is:

- `continue_paper_soak`

## Allowed Manual Outcomes

Only these outcomes are permitted:

- `continue_paper_soak`
- `paper_soak_failed`
- `eligible_for_capital_refactor_research`
- `eligible_for_tiny_live_pilot_later`

Important:

- no automatic promotion exists
- no step in this document may set `real_money_allowed=true`
- any future tiny live pilot requires a separate explicit task and separate human approval

## Review Order

Review in this order.

### 1. Confirm freeze truth

Open:

- `live_sim/output/baseline_freeze_snapshot.json`

Verify:

- `classification` is `paper-only`
- `paper_runtime_allowed` is `true`
- `real_money_allowed` is `false`
- `ssl_verify` is `true`
- `minimum_soak_days` matches config
- active and disabled sleeves match the validated stack

### 2. Inspect multi-day soak review

Open:

- `live_sim/output/paper_soak_review.json`

Verify:

- `soak_review_status`
- `soak_days_completed`
- `required_soak_days`
- `heartbeat_health`
- `restart_count`
- `successful_restore_count`
- `state_contamination_check.passed`
- `h6_disabled_status`
- `h1_short_override_status`
- `current_paper_equity`
- `realized_pnl_since_paper_start`
- `unrealized_pnl`
- `max_paper_drawdown_fraction`
- `warning_list`
- `blocker_list`

Then inspect:

- `soak_review_criteria`

Any `fail` criterion is a no-go.

### 3. Inspect review history

Open:

- `live_sim/output/paper_soak_review_history.jsonl`

Verify over time:

- reviews are append-only
- timestamps advance
- soak days progress upward
- no unexplained jumps in blockers or warnings
- equity and realized PnL evolve consistently with runtime history

### 4. Inspect daily paper report

Open:

- `live_sim/output/paper_soak_daily_report.json`

Verify:

- `promotion_criteria.promotion_status` remains a paper-soak status, not a live status
- `real_money_allowed` is `false`
- `active_sleeves` and `disabled_sleeves` remain correct
- `h6_route_counts.h6_standard = 0`
- `h6_route_counts.h6_moonshot = 0`
- `h1_short_override_active = true`
- `allocator_decision_counts` and `strategy_daily_evidence` look operationally sane

### 5. Verify no state contamination

Check:

- `paper_soak_review.json`
- `paper_runtime_startup_report.json`
- `portfolio_runtime_state.json`

Required truth:

- restore path points only to `live_sim/output/portfolio_runtime_state.json`
- no restored path points into `backtest/output`
- no restored path points into any holdout artifact directory
- no backtest or holdout trades appear as open paper positions

### 6. Verify restart safety

Open:

- `live_sim/output/paper_runtime_events.jsonl`

Verify:

- new startup events append on restart
- `restore_happened` is consistent with the actual runtime state
- `restored_positions_count` is plausible
- `validation_boundary` remains fixed
- `first_processed_timestamp_after_restore` moves forward safely

### 7. Verify dashboard truth

The dashboard is read-only.

Check:

- readiness panel
- paper soak section
- paper soak review section
- artifact freshness section
- baseline freeze section

Dashboard must agree with artifact truth for:

- `classification`
- `paper_runtime_allowed`
- `real_money_allowed`
- `ssl_verify`
- `validated_boundary`
- soak days
- active and disabled sleeves
- open positions
- artifact freshness

If dashboard and artifacts disagree, trust artifacts first and treat the dashboard as stale.

## Strict No-Go Criteria

Manual review must fail or remain paper-only if any of the following are true:

- soak days are below the configured minimum
- any operational blocker exists
- `ssl_verify` is `false`
- heartbeat is stale
- required artifacts are stale or missing
- `real_money_allowed` is unexpectedly `true`
- state contamination is detected
- backtest or holdout trades appear in paper state
- `6H` routed any trades while disabled
- `1H` short override is broken
- paper drawdown exceeds the acceptable threshold
- paper PnL is materially worse than expectation
- runtime restarts are unsafe
- dashboard disagrees with artifact truth

## Outcome Guidance

Use this mapping.

### continue_paper_soak

Use when:

- soak duration is still below minimum
- no-go failure is not present, but evidence is still too thin
- warnings still need more time to resolve through forward paper evidence

### paper_soak_failed

Use when:

- any no-go condition fails
- artifact integrity is broken
- contamination is detected
- restart safety is not credible
- disabled sleeves or side overrides are not obeyed

### eligible_for_capital_refactor_research

Use when:

- forward paper evidence is operationally clean
- minimum soak duration is met
- real money still remains blocked
- system appears stable enough to justify separate research on capital expression
- no capital-expression change is started in this step

### eligible_for_tiny_live_pilot_later

Use only when:

- minimum soak duration is met
- operational artifacts are clean
- no-go conditions are absent
- the review team explicitly agrees that the paper evidence is strong enough

This outcome still does not authorize live trading.
It only means a future tiny live pilot can be scoped in a separate task.

## Freeze Rule After Step 8

After this procedure is added:

- freeze infrastructure
- keep the dashboard read-only
- let paper soak continue
- do not start capital-expression refactor yet
- do not enable real money
