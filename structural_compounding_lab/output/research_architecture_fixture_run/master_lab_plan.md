# Structural Compounding Lab Master Plan

This validation ladder is research-only and does not auto-run expensive stages.

## Stages

- `plan_spec` | symbols=['BTCUSDT'] | auto_run=False
- `unit_tests` | symbols=['BTCUSDT'] | auto_run=False
- `smoke_window` | symbols=['BTCUSDT'] | auto_run=False
- `diagnostic_fast_window` | symbols=['BTCUSDT'] | auto_run=False
- `stress_bull_window` | symbols=['BTCUSDT'] | auto_run=False
- `stress_bear_window` | symbols=['BTCUSDT'] | auto_run=False
- `stress_chop_window` | symbols=['BTCUSDT'] | auto_run=False
- `recent_holdout` | symbols=['BTCUSDT'] | auto_run=False
- `execution_cost_sensitivity` | symbols=['BTCUSDT'] | auto_run=False
- `full_history_confirmation` | symbols=['BTCUSDT'] | auto_run=False
- `monte_carlo` | symbols=['BTCUSDT'] | auto_run=False
- `paper_candidate_later` | symbols=['BTCUSDT'] | auto_run=False
- `manual_promotion_review` | symbols=['BTCUSDT'] | auto_run=False

## Acceptance Criteria

- holdout must remain positive after research-only costs
- average R should improve or remain stable
- drawdown must not worsen materially
- missed-winner rate from waiting for pullback must remain bounded
- candidate remains non-authoritative until manual promotion review

## No-Go Rules

- no live or paper runtime mutation
- no full-history auto-run on import
- no hard gating from MACD/Bollinger by default
- no automatic promotion
- no 6H enablement
- no real-money permissions
