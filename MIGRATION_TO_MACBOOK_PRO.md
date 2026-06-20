# MIGRATION TO MACBOOK PRO

## Executive Summary

GitHub migration is feasible, but **GitHub clone alone will not reproduce the entire current working folder** because large historical data and most generated research outputs are intentionally outside the preferred commit scope. The safe path is:

1. push source, tests, docs, configs, scripts, and migration docs
2. clone on Mac
3. rebuild the BTCUSDT historical archive from public Binance klines
4. rebuild the structural research courts in the documented order
5. verify the expected classifications and safety flags

## What Should Be Pushed

- source code under the active Structural Compounding Lab
- shadow-forward runtime, watchtower, updater, and pilot automation code
- tests, docs, configs, and helper scripts
- migration docs and audit manifests
- preserved legacy Retail Trading System code that is already tracked or intentionally reusable

## What Should Not Be Pushed

- secrets or `.env` material
- root `data_storage/` BTC history unless you explicitly decide to use Git LFS
- generated `structural_compounding_lab/output/*` courts unless a tiny deterministic fixture is intentionally selected
- caches, build outputs, screenshots, `__pycache__`, `.next`, `node_modules`

## Git LFS

Git LFS is **not required** for the preferred migration path because the large BTC history can be rebuilt on the Mac from public klines. Use Git LFS only if you deliberately want GitHub to carry the root BTC archive files.

## BTCUSDT Data Strategy

- root BTC historical archive: rebuild on Mac
- canonical structural shadow-forward tape: either preserve the small ~10 MB canonical CSV or rebuild it with the fresh updater after the root archive exists
- live runtime CSV: do not treat it as migration anchor material

Important `.gitignore` nuance:

- the broad `data_storage/` ignore rule currently also catches `structural_compounding_lab/data_storage/`
- that means the canonical structural BTC tape will **not** move through Git unless you explicitly force-add it
- default recommendation remains: rebuild it on Mac unless you deliberately approve carrying that small canonical CSV

## Shadow Validation State To Preserve

- trusted BTC `1H` baseline remains the best proven engine
- `6H` context is accepted as research-only context
- `6H` native execution remains weak/rejected
- `12H` execution remains retired
- shadow-forward spec is ready
- observer is ready
- watchtower is ready but still waiting for the full `90` forward days
- fresh updater and pilot automation are ready
- future `EUR 25,000` capital anchor remains diagnostic only

## Exact Mac Setup Flow

See `MIGRATION_PLAN.md` for the detailed rebuild chain.

Quick bootstrap:

```bash
git clone <repo-url>
cd Retail-Trading-System
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main_download.py --symbol BTCUSDT --interval 1m --start-date 2018-01-01 --end-date 2026-06-13
python main_download.py --symbol BTCUSDT --interval 1m --start-date 2025-12-13 --end-date 2026-06-13
python -m structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater --mode update_and_catchup
```

Then continue with the rebuild ladder in `migration_audit/artifact_rebuild_chain.csv`.

## Safety

- `research_only=true`
- `paper_allowed=false`
- `live_allowed=false`
- `real_money_allowed=false`
- `behavior_change_allowed=false`
- future capital anchor recorded for planning only
- no broker, order, paper, or live activation should occur during migration or rebuild
