# Mac Rebuild Completion Report

## Repository and environment

- Project root: `/Users/mac/Documents/Retail-Trading-System`
- Branch: `codex/paper-readiness-cockpit-scaffold`
- Commit used: `b11584d00a04dae31572277c0424d14df30bca83`
- Python: `3.11.15`
- Virtual environment: `/Users/mac/Documents/Retail-Trading-System/.venv311`
- Python source: Homebrew `python@3.11`
- Dependencies: installed from `requirements.txt`

No commit or push was performed.

## Migration documents used

- `README.md`
- `MIGRATION_PLAN.md`
- `MIGRATION_TO_MACBOOK_PRO.md`
- `migration_audit/recreate_btcusdt_data_on_mac.md`
- `migration_audit/artifact_rebuild_chain.csv`
- `migration_audit/expected_rebuild_verification_targets.json`
- `migration_audit/final_rebuild_verification_checklist.md`
- `migration_audit/mac_rebuild_path_fix_report.md`

The actual dependency graph was longer than `artifact_rebuild_chain.csv`.
Omitted prerequisite courts were rebuilt and recorded in
`migration_audit/mac_artifact_rebuild_run_log.csv`.

## BTCUSDT data rebuild

Data rebuilt: yes.

### Root archives

- `data_storage/BTCUSDT/1m/BTCUSDT_1m_2018-01-01_to_2026-06-13.csv`
  - rows: `4,434,313`
  - first timestamp: `2018-01-01T00:00:00`
  - last timestamp: `2026-06-13T00:00:00`
- `data_storage/BTCUSDT/1m/BTCUSDT_1m_2025-12-13_to_2026-06-13.csv`
  - rows: `262,081`
  - first timestamp: `2025-12-13T00:00:00`
  - last timestamp: `2026-06-13T00:00:00`

### Canonical shadow-forward CSV

- Path:
  `/Users/mac/Documents/Retail-Trading-System/structural_compounding_lab/data_storage/BTCUSDT/1m/btcusdt_1m_canonical_shadow_forward.csv`
- First timestamp: `2025-12-13T00:00:00`
- Last timestamp: `2026-06-20T20:59:00`
- Row count: `273,420`
- Gap count: `0`
- Missing-minute count: `0`
- Duplicate timestamp count: `0`
- OHLC sanity failures: `0`
- Negative-volume failures: `0`
- Incomplete current hour excluded: yes
- Future candles rejected through latest-safe boundary: yes
- Public source: `binance_public_klines`
- Private API key used: no
- Account endpoint used: no
- Order endpoint used: no
- Broker endpoint used: no

The local `.env` contains credential fields. Every downloader/updater command
explicitly set both credential variables to empty values, and no credential
value was read or printed.

## Artifact reconstruction

Restored courts include:

- broad historical structural replay
- frozen patch and broad patch validation
- broad patch bluntness/accounting
- rolling five-year mission viability
- equal-highs forensic rescue
- support-room repair
- native pre-entry SR enrichment
- native SR-aware replay
- native strict stress and Monte Carlo
- five-year mission-gap and milestone bridge courts
- milestone fragility repair
- trusted execution-cost baseline
- repaired `12H` execution rejection
- milestone/earned gear courts
- `1H + 6H` context reconciliation
- `6H` native execution scout
- shadow-forward validation specification
- shadow observer
- watchtower
- fresh updater
- pilot automation

### Frozen-rule recovery note

The ignored Windows discovery ledger needed to regenerate the frozen short
bucket was unavailable. Seven regression fixtures consistently preserve the
same immutable frozen bucket:

`short|sweep_high|elite_convexity|resistance|equal_highs`

Only that frozen artifact field was recovered from the regression contract.
No thresholds were retuned and no archetype was selected from broad-history
performance.

## Expected target comparison

| Target | Expected | Rebuilt | Result |
| --- | --- | --- | --- |
| Trusted `1H` rolling 5Y average | `792824.56` | `792824.55832` | Match |
| Trusted `1H` rolling 5Y median | `786049.45` | `786049.44639` | Match |
| Trusted `1H` 1M-hit windows | `12` | `12` | Match |
| `6H` context classification | `SIX_H_CONTEXT_IMPROVES_1H_RESEARCH_ONLY` | same | Match |
| `6H` best context variant | `LIGHT_BOOST_6H_CONFLUENCE` | same | Match |
| `6H` context rolling average | `881465.53` | `881465.531787` | Match |
| `6H` context rolling median | `878431.05` | `878431.045803` | Match |
| `6H` native execution | `SIX_H_NATIVE_EXECUTION_WEAK` | same | Match |
| `12H` execution | retired/rejected | `NATIVE_12H_EXECUTION_REJECTED` | Match |
| Shadow specification | `SHADOW_SPEC_READY_WITH_6H_CONTEXT_RESEARCH_ONLY` | same | Match |
| Shadow observer | `SHADOW_OBSERVER_READY_RESEARCH_ONLY` | same | Match |
| Watchtower | `WATCHTOWER_READY_BUT_WAITING_FOR_FORWARD_DAYS` | same | Match |
| Pilot automation | `AUTOMATION_READY_FOR_MANUAL_APPROVAL` | same | Match |
| Future candidate capital | `25000` | `25000` | Match |
| Projected 5Y reference | `1062500` | `1062500` | Match |
| Capital anchor diagnostic only | `true` | `true` | Match |
| `paper_validation_ready` | `false` | `false` | Match |

The native mission-gap precursor rebuilt at `22` 1M-hit windows versus the
README narrative around `21`; the subsequent frozen milestone bridge retest
reproduced `21` windows and approximately `EUR 1.089M`, so the trusted
downstream baseline and all required target metrics matched.

## Final research classifications

- Trusted BTC `1H` baseline: restored
- `6H` context: restored as research-only context
- `6H` native execution: weak/rejected
- `12H` native execution: rejected/retired
- `12H`, `1D`, `1W`: diagnostic only
- Aggressive 300k gear: shadow-log/research comparison only
- Shadow specification: ready, research only
- Observer: ready, research only
- Watchtower: ready, waiting for forward days
- Fresh updater: ready, public klines only
- Pilot automation: ready for manual approval
- Paper validation: not ready

## Shadow runtime status

- Self-check: `AUTOMATION_SELF_CHECK_PASSED`
- Daily status: `YELLOW`
- Daily warning: `scheduler_not_installed_yet`
- Pilot days completed: `7`
- Full shadow days represented: `8`
- Observed forward `1H` decisions: `189`
- Canonical data gaps: `0`
- Scheduler installed: no
- `paper_validation_ready`: `false`

The canonical tape is fresh and gap-free. The only remaining yellow condition
is that the scheduler has not been installed; no scheduler installation was
performed during this migration rebuild.

## Tests

All required tests passed under Python 3.11:

- Fresh BTCUSDT updater: `6/6`
- Shadow-forward watchtower: `6/6`
- Shadow-forward pilot automation: `6/6`
- Shadow-forward observer: `3/3`
- Structural dashboard and telemetry: `15/15`
- Project paths/config loading: `5/5`

Total: `41/41` passed.

`git diff --check` and Python compilation checks passed.

Final operational freshness rerun:

- Public rows appended: `660`
- Canonical latest timestamp: `2026-06-20T20:59:00`
- Requested final test subset: `40/40` passed

## Safety confirmation

- `research_only=true`
- `paper_allowed=false`
- `live_allowed=false`
- `real_money_allowed=false`
- `behavior_change_allowed=false`
- `no_order_path_created=true`
- no paper trade created
- no live trade created
- no broker execution created
- no account/order endpoint used for data rebuild
- EUR 25,000 anchor is diagnostic/planning-only
- EUR 25,000 anchor is not used for sizing
- `paper_validation_ready=false`

## Path changes

The complete path-change inventory is in:

`migration_audit/mac_rebuild_path_fix_report.md`

Runtime paths now resolve dynamically from the environment override, current
working directory, Git root, or pathlib parent discovery. The generic
structural backtest CLI also resolves relative source/output arguments from the
detected project root.

## Generated backups retained

- Full-history canonical initialization backup:
  `structural_compounding_lab/data_storage/BTCUSDT/1m/btcusdt_1m_canonical_shadow_forward.full_history_migration_backup_20260620.csv`
- Initial contaminated watchtower bootstrap:
  `structural_compounding_lab/output/shadow_forward_watchtower_001_bootstrap_contaminated_20260620/`
- Initial blocked earned-gear attempt:
  `structural_compounding_lab/output/earned_gear_activation_discovery_audit_001_blocked_pre_prerequisites_20260620/`

These can be deleted later after manual review if disk space is needed.

## Next recommended action

Run the public updater again near a newly closed UTC hour, then run daily status:

```bash
BINANCE_API_KEY='' BINANCE_API_SECRET='' .venv311/bin/python -m structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater --mode update_and_catchup
.venv311/bin/python -m structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation --mode daily_status
```

Continue collecting real forward watchtower days. Do not enable paper or live
trading.
