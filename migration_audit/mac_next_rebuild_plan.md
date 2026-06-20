# Mac Next Rebuild Plan

## Environment

- Project root: `/Users/mac/Documents/Retail-Trading-System`
- Python environment: `.venv311`
- Python version: `3.11.15`
- Branch: `codex/paper-readiness-cockpit-scaffold`

## Missing cargo

- Root BTCUSDT public `1m` archives under `data_storage/BTCUSDT/1m/`
- Canonical structural shadow-forward BTCUSDT tape under
  `structural_compounding_lab/data_storage/BTCUSDT/1m/`
- Generated trusted-baseline and higher-timeframe research courts
- Shadow-forward validation specification and observer artifacts
- Watchtower, fresh-updater, and pilot-automation runtime artifacts

## BTCUSDT rebuild

The root public archive will be rebuilt first with:

```bash
.venv311/bin/python main_download.py --symbol BTCUSDT --interval 1m --start-date 2018-01-01 --end-date 2026-06-13
```

The six-month observer source will then be rebuilt with:

```bash
.venv311/bin/python main_download.py --symbol BTCUSDT --interval 1m --start-date 2025-12-13 --end-date 2026-06-13
```

The canonical shadow-forward tape will be initialized or extended with:

```bash
.venv311/bin/python -m structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater --mode update_and_catchup
```

Only public Binance klines are permitted. No account, signed, order, paper,
live, broker, or private-key endpoint is allowed.

## Artifact order

After the public archives exist, regenerate the documented chain:

1. Trusted `1H` execution-cost baseline
2. Repaired `12H` native execution rejection court
3. `1H + 6H` context reconciliation
4. Earned-gear research court
5. `6H` native execution scout court
6. Shadow-forward validation specification
7. Shadow-forward observer
8. Watchtower
9. Fresh updater
10. Pilot automation

Each command and outcome will be recorded in
`migration_audit/mac_artifact_rebuild_run_log.csv`.

If an ignored historical discovery ledger is unavailable but an immutable
frozen rule is preserved consistently in regression fixtures, recover only that
frozen value, document its provenance, and do not retune it from broad history.

## Success checks

- Canonical BTCUSDT CSV exists with timestamp/OHLCV schema
- Gap and duplicate counts are zero
- OHLC relationships are valid
- No incomplete or future candles are accepted
- Expected classifications and frozen metrics are compared explicitly
- Shadow self-check and daily status execute from the Mac clone
- Required tests pass under Python 3.11+
- `research_only=true`
- `paper_allowed=false`
- `live_allowed=false`
- `real_money_allowed=false`
- `behavior_change_allowed=false`
- `no_order_path_created=true`
- EUR 25,000 capital anchor remains diagnostic only
- `paper_validation_ready=false`
