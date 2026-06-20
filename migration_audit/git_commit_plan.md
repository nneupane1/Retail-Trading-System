# Git Commit Plan

Do **not** run any of these commands until manually approved.

## Safe normal commit scope

```bash
git add README.md MIGRATION_TO_MACBOOK_PRO.md MIGRATION_PLAN.md migration_audit/
git add scripts/ structural_compounding_lab/shadow_forward/ structural_compounding_lab/config/ structural_compounding_lab/docs/ structural_compounding_lab/tests/ structural_compounding_lab/diagnostics/
git add common/structural_lab_locator.py common/dashboard_telemetry.py dashboard/app/page.tsx dashboard/components/dashboard-shell.tsx dashboard/components/structural-lab-shell.tsx tests/test_dashboard_telemetry.py tests/test_structural_compounding_dashboard.py
```

## Optional small artifact scope only if explicitly desired

```bash
git add -f structural_compounding_lab/data_storage/BTCUSDT/1m/btcusdt_1m_canonical_shadow_forward.csv
```

## Files and folders to avoid

- `.env`, `.env.*`, any secret or credential material
- `data_storage/` root historical archives unless Git LFS is explicitly approved
- `structural_compounding_lab/output/**` generated courts unless a tiny fixture is intentionally selected
- `backtest/output/**`, `live_sim/output/**`
- `dashboard/node_modules/`, `dashboard/.next/`, `dashboard/tsconfig.tsbuildinfo`
- `__pycache__/`, `.pytest_cache/`, `*.pyc`
- `tmp_*.png`, `dom_dump.txt`
- unrelated `*-TL0380786*` exploratory files until manually reviewed

## Manual-review files

- `capital/__init__.py`
- `capital/capital_lanes.py`
- `capital/capital_promotion_review.py`
- `refactor.md`
- any untracked `capital/`, `backtest/`, or `tests/` additions not strictly required for the intended migration commit

## Git LFS recommendation

- **Not required** for the preferred migration path because the large BTC archives can be redownloaded on the Mac.
- Consider Git LFS only if you explicitly choose to preserve the root `data_storage/BTCUSDT/1m/*.csv` history through GitHub rather than rebuilding it.

## Recommended commit message

```text
Document structural shadow migration and Mac rebuild plan
```

## Warning

The worktree is noisy. Review `git status --short` carefully before staging. Preserve legacy Retail Trading System areas; do not delete or silently drop them.
