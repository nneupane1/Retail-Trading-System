# Retail Trading System

A modular Python trading framework for Binance OHLCV data, multi-timeframe
feature generation, backtesting, and near-live simulation.

The system is designed around a simple principle: lose small, scale into
confirmed winners, and make every decision traceable.

## Current Architecture

```text
Retail-Trading-System/
├── config/              # JSON-backed application settings
├── data/                # Binance client, historical download, CSV loading, resampling
├── features/            # EMA, structure, compression, candle metrics
├── bias/                # Directional bias detection
├── regime/              # Higher-timeframe regime detection
├── entry/               # Breakout, retest, score, entry engine
├── position/            # Risk-based position sizing
├── pyramiding/          # Add-to-winner logic
├── sniffing/            # Trend continuation checks
├── exit/                # Stop/exit decision logic
├── simulation/          # Account, trade, simulator orchestration
├── backtest/            # Historical backtest runner, engine, CSV loggers
├── live_sim/            # Near-live simulation runner and logger
├── main_backtest.py     # Backtest entry point
├── main_live.py         # Live simulation entry point
└── requirements.txt
```

## Configuration First

Runtime settings live in [config/settings.json](config/settings.json). Strategy,
data, storage, Binance, logging, and timeframe values should be changed there
instead of being hardcoded into Python files.

Main configured areas:

- Binance base URL, kline endpoint, request timeout, retries, limits, throttling
- Default symbol
- Historical date range
- Storage path
- Timeframe rules
- Initial equity and risk per trade
- Feature periods
- Entry score threshold
- Scoring weights
- Sniffing thresholds
- Pyramiding levels
- Output directories
- Historical download checkpoint behavior

## Environment Variables

Secrets are kept out of git.

Use [.env.template](.env.template) as the local environment template:

```bash
cp .env.template .env
```

Then fill:

```text
BINANCE_API_KEY=
BINANCE_API_SECRET=
TRADING_SYSTEM_CONFIG=config/settings.json
```

The real `.env` file is ignored by git. VS Code is configured through
[.vscode/settings.json](.vscode/settings.json) to load `.env` in terminals:

```json
{
  "python.envFile": "${workspaceFolder}/.env",
  "python.terminal.useEnvFile": true
}
```

Public Binance kline data does not require API keys, but the client loads them
for future authenticated endpoints.

Binance connection behavior is controlled in JSON. Request timeout, retry
attempts, retry backoff, retryable HTTP status codes, and retry logging can be
changed in `config/settings.json` without editing Python files.

## Data Pipeline

The data layer is class-backed and resumable:

- `BinanceClient` handles Binance REST calls.
- `MarketDataDownloader` handles historical downloads, recent data, CSV loading,
  validation, checkpoints, and resume behavior.
- `TimeframeBuilder` resamples 1-minute candles into configured strategy
  timeframes.

Default configured timeframes:

```text
1m    base source data
15m   execution timeframe
1h    directional bias
5h    trend confirmation
12h   macro regime
```

## Resumable Binance Downloads

Historical 1-minute downloads are checkpointed. If a run stops because of a
network issue, process interruption, or terminal close, rerunning the same
download resumes from the last saved candle instead of starting over.

During a historical download, the system writes:

```text
data_storage/<symbol>/<interval>/
├── <symbol>_<interval>_<start>_to_<end>.csv.partial.csv
└── _checkpoints/
    └── <symbol>_<interval>_<start>_to_<end>.csv.checkpoint.json
```

On completion:

- The final CSV is written.
- Duplicate timestamps are removed.
- The partial file is cleaned up.
- The checkpoint remains as metadata.

Console logs show:

- Batch number
- Download window
- Rows per batch and total rows
- Progress percentage
- Elapsed time
- ETA
- Resume timestamp
- Checkpoint path
- Wait time before the next Binance request

## Feature Pipeline

`FeaturePipeline` computes configured indicators and signal columns:

- EMA fast/slow
- Rolling high and low structure
- Compression ranges
- Close-based breakout
- Candle body strength
- Upper/lower wick ratios
- Close position

Feature periods and thresholds are controlled by JSON config.

## Strategy Flow

Each 15-minute strategy step follows this order:

```text
1. BiasDetector       -> directional context
2. RegimeDetector     -> market environment score
3. ScoreEngine        -> setup quality score
4. EntryEngine        -> creates Trade if conditions pass
5. PositionSizer      -> risk-based sizing
6. PyramidingEngine   -> add only to winning trades
7. TrendSniffer       -> trend health check
8. ExitEngine         -> stop/exit decision
9. Account            -> equity and stats update
10. Loggers           -> trade and equity CSV outputs
```

## Backtesting

Run:

```bash
python main_backtest.py
```

Expected input:

```text
data_storage/<symbol>/1m/<symbol>_1m_<start>_to_<end>.csv
```

The configured defaults are in `config/settings.json`.

Outputs:

```text
backtest/output/trades.csv
backtest/output/equity.csv
```

## Live Simulation

Run:

```bash
python main_live.py
```

Live simulation:

- Fetches recent 1-minute Binance candles
- Rebuilds configured timeframes
- Detects new 15-minute candles
- Runs the same simulator core used by backtesting
- Logs live-sim trades separately

Outputs:

```text
live_sim/output/trades.csv
```

## Object Model

The codebase is now structured around small OOP components with compatibility
wrapper functions where older imports existed.

Important classes:

- `AppConfig`
- `EnvLoader`
- `BinanceClient`
- `MarketDataDownloader`
- `TimeframeBuilder`
- `FeaturePipeline`
- `CandleMetricsCalculator`
- `BiasDetector`
- `RegimeDetector`
- `ScoreEngine`
- `EntryEngine`
- `PositionSizer`
- `PyramidingEngine`
- `TrendSniffer`
- `ExitEngine`
- `Simulator`
- `Account`
- `Trade`
- `TradeLogger`
- `EquityLogger`
- `LiveTradeLogger`

## Install

```bash
pip install -r requirements.txt
```

## Safety Notes

- Do not commit `.env`.
- Rotate Binance keys if they were ever pasted into chat, logs, screenshots, or
  issue trackers.
- Treat backtest results as invalid until timeframe alignment and lookahead
  behavior have been fully audited.
- Public Binance market data can be fetched without keys; private/signed
  endpoints must use environment variables.

## Next Engineering Priorities

1. Complete forensic review of `features/`.
2. Add focused synthetic tests for indicators and lookahead behavior.
3. Audit higher-timeframe alignment in backtests.
4. Add final-open-trade handling at the end of backtests.
5. Add structured logging instead of print-only console output.
6. Add a command-line interface for download/backtest/live-sim commands.
