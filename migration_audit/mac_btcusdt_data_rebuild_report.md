# Mac BTCUSDT Data Rebuild Report

## Commands

```bash
BINANCE_API_KEY='' BINANCE_API_SECRET='' .venv311/bin/python main_download.py --symbol BTCUSDT --interval 1m --start-date 2018-01-01 --end-date 2026-06-13
BINANCE_API_KEY='' BINANCE_API_SECRET='' .venv311/bin/python main_download.py --symbol BTCUSDT --interval 1m --start-date 2025-12-13 --end-date 2026-06-13
BINANCE_API_KEY='' BINANCE_API_SECRET='' .venv311/bin/python -m structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater --mode update_and_catchup --source-csv data_storage/BTCUSDT/1m/BTCUSDT_1m_2025-12-13_to_2026-06-13.csv
```

## Public source

- Source: Binance public klines
- Endpoint type: public market data
- Private API key used: no
- Account endpoint used: no
- Order endpoint used: no
- Signed request used: no
- Broker endpoint used: no

The local `.env` contains Binance credential fields, so the rebuild commands
explicitly set both credential variables to empty values. No credential value
was read or printed.

## Root archives

| Archive | Rows | First timestamp | Last timestamp | Duplicates removed |
| --- | ---: | --- | --- | ---: |
| `data_storage/BTCUSDT/1m/BTCUSDT_1m_2018-01-01_to_2026-06-13.csv` | 4,434,313 | 2018-01-01 00:00 | 2026-06-13 00:00 | 0 |
| `data_storage/BTCUSDT/1m/BTCUSDT_1m_2025-12-13_to_2026-06-13.csv` | 262,081 | 2025-12-13 00:00 | 2026-06-13 00:00 | 0 |

## Canonical shadow-forward tape

- Path:
  `structural_compounding_lab/data_storage/BTCUSDT/1m/btcusdt_1m_canonical_shadow_forward.csv`
- First timestamp: `2025-12-13T00:00:00`
- Last timestamp: `2026-06-20T20:59:00`
- Row count: `273,420`
- Appended public rows across catch-up runs: `11,339`
- Gap count: `0`
- Duplicate count: `0`
- Monotonic timestamp order: yes
- OHLC sanity failures: `0`
- Zero/negative price failures: `0`
- Negative-volume failures: `0`
- Incomplete current UTC hour excluded: yes
- Future candles rejected by latest-safe boundary: yes
- Latest-safe timestamp at final catch-up: `2026-06-20T20:59:00`

## Initialization note

Automatic source discovery initially selected the full root archive because it
shared the same final timestamp as the six-month observer source. That produced
a full-history canonical file with 8,088 exchange-native historical missing
minutes. The generated file was preserved as:

`structural_compounding_lab/data_storage/BTCUSDT/1m/btcusdt_1m_canonical_shadow_forward.full_history_migration_backup_20260620.csv`

The canonical tape was then rebuilt explicitly from the documented six-month
source, restoring the intended compact, zero-gap shadow-forward tape.

## Safety

- `research_only=true`
- `paper_allowed=false`
- `live_allowed=false`
- `real_money_allowed=false`
- `behavior_change_allowed=false`
- `no_order_path_created=true`
- `paper_validation_ready=false`
