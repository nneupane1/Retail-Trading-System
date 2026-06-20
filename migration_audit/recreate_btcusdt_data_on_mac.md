# Recreate BTCUSDT Data On Mac

The preferred migration path is **clone code from GitHub, then rebuild BTC data locally on the Mac**.

## 1. Rebuild the root public archive

```bash
python main_download.py --symbol BTCUSDT --interval 1m --start-date 2018-01-01 --end-date 2026-06-13
```

Expected output:

- `data_storage/BTCUSDT/1m/BTCUSDT_1m_2018-01-01_to_2026-06-13.csv`

## 2. Rebuild or extend the canonical structural shadow-forward tape

```bash
python -m structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater --mode update_and_catchup
```

Expected canonical output:

- `structural_compounding_lab/data_storage/BTCUSDT/1m/btcusdt_1m_canonical_shadow_forward.csv`

## 3. Validation checks

- first timestamp should start at the historical start expected by the audit chain
- last timestamp should reach the latest safe closed minute available at run time
- gap count must be `0` in the updater summary
- duplicate count must be `0` in the updater summary
- updater must report `public_fetch_source=binance_public_klines`
- no account, broker, paper, or live order path is allowed

## 4. Resume behavior later

The canonical updater is append-only and resume-capable. Re-run:

```bash
python -m structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater --mode update_and_catchup
```

It should continue from the last canonical timestamp rather than rebuilding from zero.
