# Retail Trading System

Retail Trading System is a modular Python trading framework for Binance OHLCV
market data. It is built around one central idea: a trend-following strategy
should make every decision from closed candles, risk a controlled fraction of
capital, hold winners as long as structure remains healthy, and scale only when
the market proves the trade right.

This repository is not a generic indicator collection. It is a complete trading
pipeline with configuration, data ingestion, resampling, feature generation,
context detection, entry logic, risk-based sizing, pyramiding, exit handling,
accounting, and CSV audit trails for both backtesting and near-live simulation.

The codebase is deliberately modular. Each folder owns one stage of the system,
and the simulator orchestrates those stages one candle at a time. The result is
a strategy path that is traceable from raw Binance candles all the way to final
trade PnL.

## Table of Contents

- [System Overview](#system-overview)
- [Architectural Philosophy](#architectural-philosophy)
- [Repository Map](#repository-map)
- [High-Level Operating Model](#high-level-operating-model)
- [Operational Workflow](#operational-workflow)
- [Timeframe Hierarchy](#timeframe-hierarchy)
- [Configuration Model](#configuration-model)
- [Current Research Baseline](#current-research-baseline)
- [Console Experience](#console-experience)
- [Data Layer](#data-layer)
- [Feature Layer](#feature-layer)
- [Context Layer](#context-layer)
- [Entry Layer](#entry-layer)
- [Risk and Trade Management](#risk-and-trade-management)
- [Simulation Core](#simulation-core)
- [Backtest Mode](#backtest-mode)
- [Live Simulation Mode](#live-simulation-mode)
- [Outputs and CSV Schemas](#outputs-and-csv-schemas)
- [Testing and Verification](#testing-and-verification)
- [Design Invariants](#design-invariants)
- [Known Constraints and Current Boundaries](#known-constraints-and-current-boundaries)
- [Extension Guide](#extension-guide)
- [Quick Start](#quick-start)
- [Dependencies](#dependencies)

## System Overview

At the broadest level, the system ingests one-minute Binance candles, rebuilds
the strategy's higher timeframes, computes all derived features, waits for a
closed 15-minute execution candle, and then lets the simulator evaluate whether
the market context supports a long entry, whether a setup is strong enough to
trade, how large the position should be, whether an open trade can be added to,
and when that trade should be exited.

The locked production-style research baseline is currently long-only. The
repository now also contains a side-aware directional engine that can evaluate
long and short candidates on the same candle, but that short branch remains
under validation rather than promoted as the default baseline.

The active long baseline uses a higher-timeframe directional bias, a regime
score that blocks weak environments, an event-based breakout trigger, a
point-based setup score, risk-based sizing, staged pyramiding, a tolerant
trend-health check for holding winners, and a hard structural stop for capital
protection.

The same simulator core is reused in both historical backtesting and near-live
simulation. That is an important architectural choice: the system does not keep
separate strategy logic for "research mode" and "live mode." It keeps one
decision engine and changes only the data source and execution loop.

### At a Glance

| Attribute | Current Behavior |
| --- | --- |
| Venue | Binance spot-style OHLCV market data |
| Source granularity | `1m` base candles |
| Execution clock | Closed `15m` candles only |
| Direction | Locked baseline: long-only; research engine: long + short capable |
| Bias filter | `1h` price vs EMA and relative EMA slope |
| Regime filter | `12h` macro + `5h` trend confirmation |
| Entry trigger | Event-based breakout above prior rolling high |
| Sizing model | Risk per trade as a fraction of equity |
| Scaling model | Add to winners at configured `+R` levels |
| Soft exit | Trend health deterioration |
| Hard exit | Intrabar touch of structural stop, executed at stop price |
| Audit trail | Trade CSVs and equity CSVs |
| Debug control | Global `app.debug` flag in config |

## Architectural Philosophy

The system follows a strict separation of concerns. Raw market data is prepared
before any decision logic sees it. Context modules determine whether conditions
are directionally supportive. Entry modules decide whether a specific execution
candle justifies a trade. Risk modules decide how much capital may be exposed.
Management modules decide whether to hold, scale, or exit. Logging modules
persist every outcome for later forensic review.

This separation matters because trading systems tend to become unreliable when
signal generation, state management, and accounting are mixed together. In this
repository, the simulator is intentionally thin. It asks other modules for one
decision each, then applies those decisions to the current trade and account.
That makes the strategy path inspectable and testable.

The project also favors event-based decisions over static state checks wherever
timing quality matters. Breakouts are detected when price crosses a level, not
merely because price remains above it. Pyramiding is triggered when price crosses
the next `+R` level, not merely because price already lives above that level.
This event-driven style reduces late entries and repeated signals.

## Repository Map

| Path | Responsibility |
| --- | --- |
| `config/` | JSON-backed configuration loader and environment handling |
| `common/` | Shared runtime helpers such as debug-output control |
| `data/` | Binance client, historical download logic, CSV loading, resampling |
| `features/` | Indicator helpers, candle metrics, and the feature pipeline |
| `bias/` | Directional market bias detection |
| `regime/` | Higher-timeframe environment scoring |
| `entry/` | Breakout, retest, scoring, and entry conversion |
| `position/` | Risk-based position sizing |
| `pyramiding/` | Add-to-winner logic and risk-budget capping |
| `sniffing/` | Trend-health evaluation for holding trades |
| `exit/` | Hard exit logic |
| `simulation/` | Trade state, account state, and simulator orchestration |
| `backtest/` | Historical runner, engine, and CSV loggers |
| `live_sim/` | Near-live runner, candle clock, and live trade logger |
| `tests/` | Focused unit and regression tests for the system's critical behavior |
| `main_download.py` | CLI entry point for resumable historical `1m` downloads |
| `main_resample.py` | CLI entry point for rebuilding and saving higher timeframes |
| `main_backtest.py` | CLI entry point for full historical runs |
| `main_live.py` | CLI entry point for near-live polling and execution |
| `main_walkforward.py` | CLI entry point for walk-forward validation and controlled branch testing |
| `main_monte_carlo.py` | CLI entry point for Monte Carlo and trade-concentration robustness analysis |

## High-Level Operating Model

The following diagram summarizes the full pipeline from raw market data to
trade results.

```mermaid
flowchart TD
    A[Binance 1m OHLCV] --> B[MarketDataDownloader]
    B --> C[TimeframeBuilder]
    C --> D[15m Execution Frame]
    C --> E[1h Direction Frame]
    C --> F[5h Trend Frame]
    C --> G[12h Macro Frame]
    D --> H[FeaturePipeline]
    E --> I[FeaturePipeline]
    F --> J[FeaturePipeline]
    G --> K[FeaturePipeline]
    I --> L[BiasDetector]
    J --> M[RegimeDetector]
    K --> M
    H --> N[ScoreEngine]
    H --> O[EntryEngine]
    O --> P[PositionSizer]
    P --> Q[Simulator]
    L --> Q
    M --> Q
    N --> Q
    Q --> R[PyramidingEngine]
    Q --> S[TrendSniffer]
    Q --> T[ExitEngine]
    Q --> U[Trade]
    Q --> V[Account]
    U --> W[Trade CSV]
    V --> X[Equity CSV]
```

The simulator operates on one execution candle at a time. In backtesting, that
means iterating through historical `15m` candles. In live simulation, that
means polling recent `1m` data until a new closed `15m` candle appears. In both
modes, the internal strategy logic is identical once the current execution row
and higher-timeframe slices are available.

## Operational Workflow

The project now supports a practical end-to-end command-line workflow rather
than assuming everything starts from `main_backtest.py`.

| Step | Command | Purpose |
| --- | --- | --- |
| `1` | `python main_download.py` | Download and checkpoint local `1m` history from Binance |
| `2` | `python main_resample.py` | Optional: materialize `15m`, `1h`, `5h`, and `12h` CSVs for inspection |
| `3` | `python main_backtest.py` | Run the full historical strategy pipeline with Rich progress UI and resume support |
| `4` | `python main_walkforward.py --scheme multifold --branch-spec ...` | Run controlled multi-fold validation across candidate branches |
| `5` | `python main_monte_carlo.py ...` | Stress-test completed trades with bootstrap and concentration analysis |
| `6` | `python main_live.py` | Run near-live simulation using local warmup history plus fresh Binance `1m` candles |

Two practical clarifications matter:

- `main_backtest.py` already resamples and computes features internally, so
  `main_resample.py` is optional for strategy correctness.
- `main_live.py` now bootstraps from local `1m` history first, then merges
  recent Binance candles into that in-memory state before resampling.

## Timeframe Hierarchy

The system is intentionally multi-timeframe. Each timeframe has a dedicated job
and is not interchangeable with the others.

| Timeframe | Role | Current Use |
| --- | --- | --- |
| `1m` | Base market data | Downloaded from Binance and resampled upward |
| `15m` | Execution timeframe | Entries, pyramiding checks, exits, candle metrics |
| `1h` | Direction timeframe | Bias detection |
| `5h` | Trend confirmation timeframe | Regime scoring via structure confirmation |
| `12h` | Macro timeframe | Regime scoring via structure and slope |

### Why the hierarchy matters

The design prevents the execution layer from making decisions without broader
context. A `15m` breakout is not enough on its own. The system first asks
whether the `1h` direction is aligned and whether the `12h`/`5h` environment is
at least moderate. This reduces the chance that a locally strong candle is
traded in a larger weak or sideways market.

### Candle alignment and lookahead control

Resampled candles are right-labeled and treated as closed units. Higher-timeframe
slices are always restricted with `.loc[:current_execution_timestamp]` before
the simulator sees them. That means the strategy only sees higher-timeframe bars
that would already have been complete at the execution timestamp being tested.

## Configuration Model

All runtime behavior is driven by [`config/settings.json`](config/settings.json).
The project treats configuration as part of the system definition. Strategy
weights, thresholds, timeframes, paths, retry behavior, and logging behavior are
not scattered across the codebase.

### Configuration sources

1. JSON file: `config/settings.json`
2. Optional environment file: `.env`
3. Optional override path: `TRADING_SYSTEM_CONFIG`

### Core configuration sections

| Section | Purpose |
| --- | --- |
| `app` | Default symbol and debug switch |
| `account` | Initial equity and risk per trade |
| `backtest` | Backtest output directory |
| `binance` | Network, retry, timeout, and request behavior |
| `downloads.history` | Checkpointing and resume behavior |
| `entry` | Score threshold required to convert a setup into a trade |
| `features` | EMA periods, structure windows, compression windows, candle metrics |
| `history` | Backtest date range |
| `live_sim` | Live output directory and polling interval |
| `position` | Minimum stop-distance safeguards and optional size caps |
| `storage` | Base data directory |
| `strategy.bias` | Bias EMA and slope threshold |
| `strategy.regime` | Regime weights, slope threshold, and regime bands |
| `strategy.scoring` | Entry score weights and candle-quality thresholds |
| `strategy.sniffing` | Hold/exit thresholds for trend health |
| `strategy.pyramiding` | Add levels and total risk budget |
| `timeframes` | Base, execution, direction, trend, macro, resample settings |

### Environment variables

The repository includes [`.env.template`](.env.template). The typical local
variables are:

```text
BINANCE_API_KEY=
BINANCE_API_SECRET=
TRADING_SYSTEM_CONFIG=config/settings.json
```

Public OHLCV requests do not require keys, but the Binance client is prepared
to load credentials for future authenticated endpoints.

### Debug control

The global switch is:

```json
"app": {
  "default_symbol": "BTCUSDT",
  "debug": true
}
```

When `app.debug` is `false`, the internal print-heavy modules route their output
through `common/debug.py` and remain silent. This is a practical middle ground
between development verbosity and a fully structured logging framework.

## Current Research Baseline

The repository now contains a materially refined research baseline rather than
only the original breakout skeleton. The locked baseline remains fully
rule-based and inspectable, and it now sits beside a larger research harness
for controlled branches, walk-forward drift analysis, Monte Carlo robustness,
and an experimental long+short engine.

### Active entry refinements

The current baseline keeps the additive score model, then applies narrow
config-driven filters in the entry-conversion layer:

| Refinement | Active behavior |
| --- | --- |
| Score threshold | `entry.score_threshold = 4` |
| Compression filter | `entry.block_compression = true` |
| Score bucket exclusion | `entry.blocked_scores = [7]` |
| Score-specific body filter | Score `8` requires `body_strength >= 2.0` |
| Score-specific wick filter | Score `8` rejects `0.1 <= upper_wick_ratio < 0.3` |

### Directional research extensions

The codebase now supports a unified directional engine even though the locked
baseline still runs long-only by default.

Directional research additions include:

| Capability | Current implementation |
| --- | --- |
| Unified side selection | Competing `LONG` vs `SHORT` scores on the same `15m` candle |
| Bearish structure events | `breakdown` event below prior rolling low |
| Side-aware trade math | Shared `Trade` object with `side`, mirrored stops, mirrored PnL |
| Side-aware regime scoring | Bullish and bearish `12h` / `5h` environment scoring |
| Side-aware hold logic | Short trades use mirrored wick/close logic and a VWAP guard |
| Side-aware hard stops | Long exits on `low <= stop`; short exits on `high >= stop` |
| Side-aware pyramiding | Mirrored `-R` event triggers for shorts |

These directional branches are intentionally treated as research candidates, not
as a silently promoted replacement for the stronger locked long baseline.

### Active winner-retention behavior

The current baseline uses profit-aware soft-exit relaxation:

| Stage | Active behavior |
| --- | --- |
| Base hold logic | Price must hold above the fast EMA and pass candle-quality confirmation rules |
| Proven winner | After `+1R`, candle-quality confirmations can relax to `0` |
| Elite winner | After `+1.5R`, the anchor can switch from the fast EMA to the slow EMA |

### Active selective pyramiding behavior

Pyramiding is no longer a blanket add-to-winner rule. It is now quality-gated.

For a trade to qualify for elite pyramiding, the open position must already be
at least `+1R`, and the current execution candle must satisfy enough of these
conditions:

- `body_strength >= 1.5`
- `upper_wick_ratio <= 0.6`
- `close_position >= 0.75`
- at least `2` confirmations across those conditions

Current configured add structure:

| Level | Trigger | Base size fraction | Elite behavior |
| --- | --- | --- | --- |
| `1` | `+1R` cross | `0.5` | Standard |
| `2` | `+2R` cross | `0.5` | Multiplied by `1.5`, so effective add size is `0.75` |

Risk budgets are also split:

| Case | Max total stop-risk budget |
| --- | --- |
| Normal trade | `1.0x` configured trade risk |
| Elite pyramiding trade | `2.5x` configured trade risk |

### Active hard-stop model

The stop model is now internally consistent and materially more realistic than
the original implementation:

```text
trigger: low <= stop_price
execution: exit at stop_price
```

### Latest validated backtest snapshot

Using the current locked long baseline on the configured historical range
`2018-01-01 -> 2026-05-22`, the latest full rerun produced:

| Metric | Latest result |
| --- | --- |
| Initial equity | `20000.00` |
| Final equity | `43678.91` |
| Net PnL | `+23678.91` |
| Trades | `741` |
| Win rate | `42.24%` |
| Profit factor | `1.454` |
| Average `pnl_R_initial` | `0.1124` |
| Max drawdown | `-12.17%` |

This is a research snapshot, not a live-performance claim. Its importance is
that the current system is now behaving like a concentrated profit-distribution
engine rather than a flat, overtrading breakout script.

### Controlled validation state

Recent multi-fold validation work produced two important conclusions:

- conditional `score 5` pruning is worth testing, but blunt removal still harms
  fold stability even when it improves average edge
- the new long+short engine is functionally complete, but the first short
  branches remain weaker than the locked long baseline and therefore are not
  yet promoted

## Console Experience

The repository now exposes a much cleaner terminal UX than a traditional
print-spam research script.

### Historical download dashboard

`main_download.py` uses a Rich live dashboard that shows:

- colored progress bar
- batch number and current time window
- rows saved and estimated completion
- TLS mode and checkpoint path
- recent events such as retries, saves, resumes, and completion

### Backtest dashboard

`main_backtest.py` uses a separate Rich live dashboard that shows:

- processed execution candles and percent complete
- elapsed time and ETA
- current equity and net PnL
- trade count, wins, losses, and win rate
- recent pipeline events such as load, resample, feature build, resume, and completion

During a dashboard-driven backtest, the framework force-suppresses module debug
spam so the screen stays readable.

## Data Layer

The data layer transforms external market data into a local, validated, and
resampled dataset that the strategy can trust.

### BinanceClient

`data/binance_client.py` is the lowest-level network module. It encapsulates the
Binance REST request, timeout behavior, retry logic, throttle spacing, and
response handling. It also supports `ssl_verify` and `ca_bundle_path`, which is
useful in corporate environments with custom certificate chains. It is
deliberately small, because its job is not strategy logic. Its job is to return
raw klines reliably.

### MarketDataDownloader

`data/downloader.py` owns the higher-level market-data workflow:

- downloading historical `1m` candles
- resuming interrupted downloads
- checkpoint writing and reading
- partial CSV accumulation
- duplicate removal
- closed-candle validation
- fetching recent candles for live simulation
- loading local CSVs into pandas DataFrames

### Historical checkpointing

Historical downloads are resumable. During a long run, the system keeps:

| Artifact | Purpose |
| --- | --- |
| `*.partial.csv` | Incrementally appended unfinished candle history |
| `*.checkpoint.json` | Resume cursor and download metadata |
| Final `*.csv` | Clean deduplicated completed history |

This means a multi-hour download can survive network interruption or terminal
closure without restarting from the first candle.

The checkpoint writer also retries Windows file-replace operations to reduce
crashes caused by transient OneDrive or indexing locks.

If you extend the configured end date, the downloader can also bootstrap the
new target range from the newest compatible completed CSV for the same symbol,
interval, and start date. That means extending a file such as
`..._to_2026-05-12.csv` to `..._to_2026-05-22.csv` does not require a full
redownload from `2018-01-01`.

### TimeframeBuilder

`data/resampler.py` rebuilds higher-timeframe OHLCV bars from the `1m` base
stream. The builder:

1. resamples `open`, `high`, `low`, `close`, and `volume`
2. drops any still-incomplete higher-timeframe candle
3. saves each timeframe to its configured storage path

The key correctness property is that incomplete resampled candles are removed
before strategy logic sees them. That is essential for both backtesting realism
and live-simulation consistency.

## Feature Layer

The feature layer is the analytical foundation of the strategy. It converts raw
OHLCV bars into the exact columns consumed by bias, regime, scoring, entry,
pyramiding, and exit logic.

### Feature pipeline responsibilities

`features/feature_pipeline.py` computes, in order:

1. trend EMAs
2. rolling structure highs and lows
3. compression ranges
4. event-based breakout columns
5. candle-quality metrics
6. NaN cleanup on all required feature columns

### Derived columns

| Column family | Meaning |
| --- | --- |
| `ema20`, `ema50` | Fast and slow trend filters |
| `hh20` | Rolling structural high |
| `ll10` | Rolling structural low |
| `range_10`, `range_30` | Short and long volatility ranges |
| `compression` | Whether short range is compressed relative to long range |
| `prev_close` | Prior close, used for event logic |
| `hh20_prev` | Prior structural high |
| `above_breakout_level` | State flag: current close above prior high |
| `breakout` | Event flag: current close crossed above prior high |
| `body_strength` | Candle body normalized by rolling average body |
| `upper_wick_ratio` | Upper wick relative to body |
| `lower_wick_ratio` | Lower wick relative to body |
| `close_position` | Where the close sits inside the candle's range |

### Indicator helpers

`features/indicators.py` intentionally keeps low-level indicator math simple:

| Helper | Description |
| --- | --- |
| `ema(series, period)` | Exponential moving average |
| `rolling_high(series, period)` | Highest high over a rolling window |
| `rolling_low(series, period)` | Lowest low over a rolling window |

### Compression

Compression is calculated by comparing a short-term price range to a longer-term
range:

```text
compression = range_fast < ratio * range_slow
```

This does not forecast direction. It marks a market condition in which price has
contracted and may be more attractive for breakout expansion.

### Breakout event logic

Breakout timing is event-based, not state-based. The pipeline computes:

```text
above_breakout_level = close > hh_prev
breakout = above_breakout_level and prev_close <= hh_prev
```

That distinction is critical. A static condition like "close above prior high"
stays true for many candles. An event-based condition becomes true only at the
moment of crossing, which is what the entry engine needs.

### Candle metrics

`features/candle_metrics.py` quantifies candle quality using normalized values
instead of pattern names. This makes the strategy more robust across different
volatility regimes and different nominal price levels.

### NaN handling

The feature pipeline explicitly drops incomplete rows at the end of the build.
That prevents early rolling-window NaNs from leaking into downstream logic and
creating false signals during warm-up periods.

## Context Layer

The context layer answers two different questions:

1. Should the system even consider the long side'
2. Is the broader market environment strong enough to permit entries'

These are separate concerns, handled by `BiasDetector` and `RegimeDetector`.

### BiasDetector

`bias/bias_detector.py` determines directional bias from the `1h` timeframe.

The logic is:

```text
bullish if close > ema and relative_ema_slope > +threshold
bearish if close < ema and relative_ema_slope < -threshold
neutral otherwise
```

The slope is relative, not absolute:

```text
slope = (current_ema - past_ema) / past_ema
```

That makes the calculation scale-independent and avoids the problem where the
same shape would produce different slope magnitudes on assets at different price
levels.

### RegimeDetector

`regime/regime_detector.py` scores the broader market environment using the
`12h` macro timeframe and the `5h` confirmation timeframe.

Current scoring inputs:

| Signal | Default Weight | Meaning |
| --- | --- | --- |
| `12h close > ema50` | `2` | Macro structure is bullish |
| `12h relative ema50 slope > threshold` | `1` | Macro trend is rising with sufficient slope |
| `5h close > ema50` | `1` | Intermediate trend confirms the macro direction |

Current bands:

| Score band | Interpretation | Entry permission |
| --- | --- | --- |
| `>= strong_score` | Strong | Allowed |
| `>= moderate_score` and `< strong_score` | Moderate | Allowed |
| `< moderate_score` | Weak | Blocked |

The regime module is intentionally conservative in scope. It currently acts as
an entry gate only. It does not yet modify exits, pyramiding, or risk per trade.

## Entry Layer

The entry layer converts a context-supported execution candle into a tradable
idea.

### ScoreEngine

`entry/scoring.py` builds a transparent additive score rather than using one
giant all-or-nothing condition. That is consistent with the broader philosophy
of reducing unnecessary strategy friction.

Current scoring components:

| Component | Default Weight | Condition |
| --- | --- | --- |
| Bias alignment | `2` | `bias == bullish` |
| Trend confirmation | `1` | `15m close > ema20` |
| Compression | `1` | `compression == True` |
| Breakout event | `2` | `breakout == True` |
| Strong body | `1` | `body_strength > body_strength_min` |
| Strong close position | `1` | `close_position > close_position_min` |
| Low upper wick | `1` | `upper_wick_ratio < upper_wick_max` |

The entry threshold currently lives under:

```text
entry.score_threshold = 4
```

### BreakoutDetector

`entry/breakout.py` duplicates the event-based breakout check as an explicit
detector module. It requires both `prev_close` and the previous structural high
column, and it computes the breakout directly from the row rather than trusting
a looser fallback.

### EntryEngine

`entry/entry_engine.py` is intentionally simple. A trade is created only if:

1. bias is bullish
2. score meets the configured threshold
3. breakout event is true

If those rules pass, the engine converts the row into a `Trade` object. It does
not size the trade. Position sizing remains a separate responsibility.

### Current refinement filters

The entry engine now supports additional config-driven filtering beyond the base
score threshold:

| Filter | Purpose |
| --- | --- |
| `entry.block_compression` | Reject setups formed during compressed conditions |
| `entry.blocked_scores` | Exclude known weak score buckets without changing the score engine |
| `entry.min_body_strength_by_score` | Require stronger momentum for specific score cohorts |
| `entry.blocked_upper_wick_ranges_by_score` | Exclude score-specific wick structures that backtest poorly |

These are intentionally placed in the entry-conversion layer rather than inside
the scoring engine. That keeps the score model interpretable while allowing
surgical filtering of weak subpopulations discovered during research.

The currently active research baseline uses all four of these refinement hooks.

### RetestDetector

`entry/retest.py` exists in the repository but is not part of the active entry
path. The current system uses breakout entries, not retest entries.

## Risk and Trade Management

This part of the system determines not only whether a trade exists, but how much
capital is exposed, whether the position may be enlarged, and whether the trade
still deserves to be held.

### PositionSizer

`position/sizing.py` uses a classical risk-based sizing formula:

```text
risk_amount = equity * risk_per_trade
risk_per_unit = abs(entry_price - stop_price)
position_size = risk_amount / risk_per_unit
```

The module also includes safety constraints:

| Safeguard | Purpose |
| --- | --- |
| `min_stop_distance_ratio` | Rejects trades with unrealistically tight stops relative to price |
| `min_stop_distance_absolute` | Rejects trades with stops below an absolute floor |
| `max_position_size_units` | Optional hard cap on unit size |
| `max_notional_equity_multiple` | Optional cap on notional exposure relative to equity |

If sizing returns `0`, the simulator now skips the trade cleanly instead of
creating a zero-size dummy position.

### PyramidingEngine

`pyramiding/pyramiding_engine.py` handles scaling into winning trades.

Its current behavior is:

| Rule | Meaning |
| --- | --- |
| Add only after trade is already profitable | Never add to a loser |
| Trigger on event cross of configured `+R` level | Avoid repeated adds while price stays above a level |
| Require `trend_ok` | Do not scale into weakening structure |
| Enforce sequential levels | Level 2 cannot fire before level 1 |
| Require a quality gate for elite adds | Only the strongest open trades unlock larger add budgets |
| Cap additions by total stop-risk budget | Prevent runaway exposure |

Default configured levels:

| Level | Trigger | Size fraction of base entry |
| --- | --- | --- |
| `1` | `+1R` | `0.5` |
| `2` | `+2R` | `0.5` |

Pyramiding uses the original entry price and original `R` as the reference for
future levels. That keeps scaling tied to the original trade structure rather
than to a floating average entry.

When the quality gate passes, the active baseline also:

- allows a larger total pyramid risk budget (`2.5x` configured trade risk)
- scales the level-2 add size by `1.5`, making the effective level-2 add
  fraction `0.75` of the base entry size

This creates a deliberate distinction between ordinary winning trades and elite
trades that have earned additional capital concentration.

### TrendSniffer

`sniffing/trend_sniffer.py` is the system's soft-exit intelligence. It asks:

> Is the trend still healthy enough to deserve being held'

Current logic:

```text
trend_alive =
    base:
        (close > fast_ema)
        and confirmations >= min_confirmations

    after +1R:
        (close > fast_ema)
        and confirmations >= relaxed_min_confirmations

    after +1.5R:
        (close > slow_ema)
        and confirmations >= relaxed_min_confirmations
```

This is deliberately profit-aware. Ordinary trades still need the fast EMA
anchor. Proven winners get more tolerance, and elite winners can be held
against the slower EMA anchor. That lets the system keep trend exposure longer
without weakening hard-stop discipline.

### ExitEngine

`exit/exit_engine.py` currently handles hard exits only. Its job is simple and
intentionally separate from trend-health logic:

```text
exit if low <= stop_price
hold otherwise
```

When a hard stop is triggered, the simulator now executes the exit at
`stop_price`, not at the candle close. That keeps realized loss aligned with
the stop-based sizing model and makes the backtest materially more honest.

The separation between `TrendSniffer` and `ExitEngine` is intentional:

- `TrendSniffer` handles soft structural weakening
- `ExitEngine` handles hard capital-protection exits

## Simulation Core

The simulator is the orchestrator that turns all module outputs into one
deterministic trade lifecycle.

### Decision sequence inside `Simulator.step()`

```mermaid
flowchart TD
    A[Current 15m row] --> B[BiasDetector on 1h slice]
    A --> C[RegimeDetector on 5h and 12h slices]
    B --> D{Open trade'}
    C --> D
    D -- No --> E{Regime allows entries'}
    E -- No --> Z[Log equity and finish]
    E -- Yes --> F[ScoreEngine]
    F --> G[EntryEngine]
    G --> H{Trade created'}
    H -- No --> Z
    H -- Yes --> I[PositionSizer]
    I --> J{Size > 0'}
    J -- No --> Z
    J -- Yes --> K[Add first trade entry]
    K --> Z
    D -- Yes --> L[TrendSniffer]
    L --> M[ExitEngine]
    M --> N{Hard exit'}
    N -- Yes --> O[Close trade]
    N -- No --> P{Trend weakened'}
    P -- Yes --> O
    P -- No --> Q[PyramidingEngine]
    Q --> R{Add triggered'}
    R -- Yes --> S[Cap by risk and add entry]
    R -- No --> Z
    O --> T[Account update and trade logging]
    T --> Z
```

### Entry path

If there is no open trade, the simulator:

1. computes bias and regime
2. blocks weak regimes before entry scoring
3. scores the execution candle
4. asks the entry engine to create a trade
5. sizes that trade
6. skips invalid zero-size trades
7. opens the trade by adding the first entry layer

### Management path

If there is already an open trade, the simulator:

1. evaluates `trend_ok`
2. evaluates the hard stop
3. exits on hard-stop breach
4. exits on trend weakness if hard stop did not fire
5. only then checks pyramiding

That ordering reflects the current implementation and keeps all trade management
in one place.

### Trade object

`simulation/trade.py` stores the full lifecycle of one position.

Key stored state:

| Field | Meaning |
| --- | --- |
| `entry_time`, `entry_price` | Original setup timing and execution price |
| `stop` | Structural stop based on rolling low |
| `R` | Initial absolute risk unit from first entry price to stop |
| `entries` | All entry layers, including pyramids |
| `conditions` | Why the trade was taken |
| `exit_time`, `exit_price` | Trade close details |
| `pnl` | Total quote-currency profit or loss |
| `pnl_R_total` | Profit relative to total deployed stop-risk |
| `pnl_R_initial` | Profit relative to first-entry stop-risk |
| `initial_risk_amount` | Risk from the initial entry only |
| `total_risk_amount` | Total risk across all layers to the shared stop |

This dual-R reporting matters because pyramiding changes total deployed risk.
The repository now preserves both interpretations explicitly.

### Account object

`simulation/account.py` tracks:

- current equity
- number of trades
- wins and losses
- win rate

Equity is updated only when a trade closes. The account does not mark to market
unrealized PnL between candles.

## Backtest Mode

Backtesting runs the full pipeline over historical candles stored in the local
data directory.

### Entry point

```bash
python main_backtest.py
```

### Historical pipeline

`backtest/runner.py` performs these stages:

1. load local `1m` CSV
2. build `15m`, `1h`, `5h`, and `12h` timeframes
3. compute features on all strategy timeframes
4. instantiate the simulator and CSV loggers
5. hand everything to `BacktestEngine`

The backtest always uses the configured `1m` history as the canonical source,
then rebuilds the higher timeframes from that source during the run. Prebuilt
`15m`, `1h`, `5h`, and `12h` CSVs are useful for inspection, but they are not
the historical execution source of truth.

### Backtest engine behavior

`backtest/engine.py` iterates through `15m` candles and slices the higher
timeframes to the current execution timestamp on every step.

The engine no longer starts from a fixed warm-up index. It now begins at the
first execution timestamp where the required `15m`, `1h`, `5h`, and `12h`
contexts all exist. That preserves realism and prevents invalid early-candle
evaluation.

### Backtest checkpointing

Historical backtests are resumable. If the process is interrupted, the engine
stores:

| Artifact | Purpose |
| --- | --- |
| `backtest/output/_checkpoints/*.checkpoint.json` | Next execution index and simulator state snapshot |
| `backtest/output/trades.csv` | Trade log continued safely on resume |
| `backtest/output/equity.csv` | Equity log continued safely on resume |

On a fresh run, the output CSVs are recreated from scratch. On a resume, the
current checkpoint and output files are reused so the run can continue from the
last saved execution step.

### Backtest outputs

By default:

```text
backtest/output/trades.csv
backtest/output/equity.csv
backtest/output/_checkpoints/<symbol>_backtest_<start>_to_<end>.checkpoint.json
```

Because output filenames embed the configured start and end dates, changing the
configured historical range produces a different output and checkpoint family.

## Live Simulation Mode

Live simulation reuses the same strategy core but replaces historical iteration
with a polling loop.

### Entry point

```bash
python main_live.py
```

### Live loop behavior

`live_sim/runner.py` continuously:

1. loads local `1m` bootstrap history from the completed CSV, or falls back to the partial CSV
2. trims that state to the required warmup window for the current feature and context stack
3. fetches the latest recent `1m` candles from Binance
4. merges, deduplicates, and sorts the in-memory `1m` state
5. rebuilds all strategy timeframes
6. recomputes features on every timeframe
7. checks whether a new `15m` candle has appeared
8. if so, slices the higher timeframes to that candle time
9. runs the same simulator step used by backtesting
10. sleeps for `live_sim.poll_seconds`

### Candle clock

`live_sim/candle_clock.py` prevents repeated execution on the same `15m`
candle. It also safely handles the case where the `15m` DataFrame is empty.

Because the live loop now depends on local bootstrap history, the intended order
is:

1. `python main_download.py`
2. `python main_live.py`

### Live outputs

By default:

```text
live_sim/output/trades.csv
```

The live loop currently logs trades but does not maintain a separate live equity
CSV by default.

## Outputs and CSV Schemas

The repository treats CSV outputs as audit artifacts, not as incidental logs.
They are designed to explain not just what happened, but why it happened.

### Backtest trade log

`backtest/output/trades.csv` columns:

| Column | Meaning |
| --- | --- |
| `side` | `long` or `short` |
| `entry_time` | First entry timestamp |
| `exit_time` | Exit timestamp |
| `entry_price` | First entry price |
| `exit_price` | Exit price |
| `stop_price` | Shared structural stop used by the trade |
| `pnl` | Quote-currency profit or loss |
| `pnl_R` | Compatibility alias for total-risk R |
| `pnl_R_total` | PnL divided by total deployed risk |
| `pnl_R_initial` | PnL divided by initial entry risk |
| `initial_risk_amount` | Risk of the first layer |
| `total_risk_amount` | Total risk of all layers to stop |
| `bias` | Directional bias at entry |
| `regime_score` | Higher-timeframe regime score at entry |
| `regime_class` | Regime label such as `strong` or `moderate` |
| `entry_threshold` | Entry threshold active when the trade was taken |
| `exit_reason` | Why the trade was closed, such as hard exit or trend weakness |
| `entry_layer_count` | Number of filled entry layers across the trade lifecycle |
| `pyramid_level` | Final pyramid depth reached by the trade |
| `score` | Entry score |
| `body_strength` | Candle metric at entry |
| `close_position` | Candle metric at entry |
| `upper_wick_ratio` | Candle metric at entry |
| `lower_wick_ratio` | Candle metric at entry |
| `compression` | Whether setup formed during compression |
| `breakout` | Whether entry candle was a breakout event |
| `breakdown` | Whether entry candle was a breakdown event |
| `session_vwap` | Session VWAP at entry |
| `vwap_distance_ratio` | Distance from VWAP at entry |
| `ema_gap_ratio` | Fast/slow EMA separation at entry |
| `atr` | ATR value at entry |
| `macd_hist` | MACD histogram at entry |

### Equity log

`backtest/output/equity.csv` columns:

| Column | Meaning |
| --- | --- |
| `timestamp` | Strategy step timestamp |
| `equity` | Account equity after that step |

### Live trade log

`live_sim/output/trades.csv` uses the same schema as the backtest trade log.

## Testing and Verification

The repository includes a focused `unittest` suite under `tests/`.

### What is covered

| Test area | Purpose |
| --- | --- |
| Breakout logic | Verify event-based breakout timing |
| Directional regime logic | Verify mirrored bearish environment scoring |
| Feature pipeline | Verify state-transition breakout marking and NaN cleanup |
| Trend sniffer | Verify tolerant hold logic |
| Pyramiding | Verify event-based adds and trend gating |
| Position sizing | Verify stop-floor safeguards and caps |
| Regime detector | Verify relative slope, thresholds, and classification |
| Simulator management | Verify entry blocking, exit ordering, and pyramiding path |
| Trade metrics | Verify total-risk and initial-risk `R` calculations |
| Loggers | Verify file creation, headers, and appended rows |
| Debug control | Verify `app.debug` actually suppresses output |
| Download checkpointing | Verify resumable writes and transient replace retries |
| TLS configuration | Verify `ssl_verify` and custom CA bundle behavior |
| Live bootstrap | Verify local warmup loading and recent-candle merge behavior |
| Backtest resume | Verify checkpoint save/restore and valid dynamic start index |

### Test command

```bash
python -m unittest discover -s tests -v
```

## Design Invariants

The following rules describe what the system is trying to guarantee at all
times.

| Invariant | Why it matters |
| --- | --- |
| Strategy decisions use closed candles only | Prevents mid-candle noise and hidden lookahead |
| Higher-timeframe slices stop at the current execution timestamp | Preserves historical realism |
| Breakout is event-based | Avoids late entries and repeated triggers |
| Pyramiding is event-based | Avoids repeated adds while price remains above a level |
| Position sizing is risk-based | Keeps capital exposure normalized across setups |
| Trend holding is tolerant, not perfectionist | Helps the system stay in large winners |
| Hard stop logic is separate from soft trend logic | Keeps capital protection distinct from trade management |
| Feature rows with incomplete rolling values are dropped | Prevents NaN contamination |
| Output CSVs preserve both setup context and performance | Supports forensic review after a run |

## Known Constraints and Current Boundaries

This section documents current boundaries so readers can distinguish design from
deliberate incompleteness.

### Strategy scope

- The locked baseline is currently long-only.
- The repo also contains an experimental long+short engine that has not yet
  beaten the locked baseline in multi-fold validation.
- `entry/retest.py` exists but is not part of the active entry path.
- Regime currently acts only as an entry gate.
- Regime does not yet reduce sizing or pyramiding in weaker-but-allowed markets.

### Execution realism

- There is no fee model.
- There is no slippage model.
- There is no partial-fill model.
- Equity is updated on realized trade close, not mark-to-market unrealized value.

### Backtest behavior

- The backtest currently rebuilds higher timeframes from canonical `1m` history
  on every run, even if prebuilt higher-timeframe CSVs already exist.
- The current engine does not explicitly force-close an open trade at the final
  candle of the dataset.
- Output files are not versioned automatically per run; a fresh completed run
  rewrites `backtest/output/trades.csv` and `backtest/output/equity.csv`.

### Logging

- Module logging is still print-based under a shared switch rather than a full
  structured logging framework.
- The Rich dashboards currently exist for historical download and backtest, not
  for the live simulation loop.

## Extension Guide

The safest way to extend the system is to preserve the same separation of
concerns that already exists.

### Recommended extension patterns

| Goal | Best extension point |
| --- | --- |
| Change thresholds or weights | `config/settings.json` |
| Add new features | `features/feature_pipeline.py` |
| Add a new context filter | `bias/` or `regime/` depending on scope |
| Add entry scoring factors | `entry/scoring.py` |
| Add a new entry style | `entry/` plus simulator integration |
| Modify sizing rules | `position/sizing.py` |
| Modify add-to-winner rules | `pyramiding/pyramiding_engine.py` |
| Modify hold/soft-exit behavior | `sniffing/trend_sniffer.py` |
| Modify hard exit behavior | `exit/exit_engine.py` |
| Add new persistence artifacts | `backtest/` and `live_sim/` loggers |

### Practical guidance

If a change affects timing, implement it as an event when possible. If a change
affects thresholds, prefer configuration over hardcoding. If a change affects
capital exposure, keep it in the sizing or pyramiding layers rather than hiding
it inside signal modules.

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Create your local environment file

```bash
cp .env.template .env
```

If you are on PowerShell and do not have `cp` aliased as expected, create the
file manually from `.env.template`.

### 3. Configure the strategy

Edit:

```text
config/settings.json
```

Minimum values to understand before running:

- `app.default_symbol`
- `history.start_date`
- `history.end_date`
- `account.initial_equity`
- `account.risk_per_trade`
- `entry.score_threshold`
- `strategy.bias.*`
- `strategy.regime.*`
- `strategy.scoring.*`
- `strategy.sniffing.*`
- `strategy.pyramiding.*`
- `app.debug`

### 4. Obtain or download `1m` history

Use the dedicated downloader:

```bash
python main_download.py
```

The downloader writes a resumable `1m` history under:

```text
data_storage/<symbol>/1m/<symbol>_1m_<start>_to_<end>.csv
```

If you want to override the range or symbol:

```bash
python main_download.py --symbol BTCUSDT --start-date 2024-01-01 --end-date 2024-12-31
```

If you extend the configured end date later, rerunning `main_download.py` will
reuse the latest compatible completed CSV as a bootstrap source before
requesting only the missing candles.

### 5. Optionally materialize higher timeframe CSVs

```bash
python main_resample.py
```

This is useful for inspection and debugging, but it is not required for
backtesting because `main_backtest.py` already resamples internally.

### 6. Run the backtest

```bash
python main_backtest.py
```

The backtest:

- rebuilds `15m`, `1h`, `5h`, and `12h` candles from the local `1m` history
- computes features on all strategy timeframes
- applies the active entry refinements, winner-retention rules, and selective pyramiding logic
- runs the shared simulator
- writes trade and equity CSVs
- shows a Rich progress dashboard
- saves checkpoints so interrupted runs can resume

### 7. Run live simulation

```bash
python main_live.py
```

The live simulation now bootstraps from local `1m` history first, then appends
fresh Binance `1m` data before each resample-and-decision cycle.

## Dependencies

The current `requirements.txt` contains:

| Package | Role |
| --- | --- |
| `pandas` | Time-series storage, rolling windows, resampling |
| `numpy` | Numerical helpers |
| `requests` | Binance HTTP requests |
| `matplotlib` | Available for analysis/visualization workflows |
| `rich` | Live terminal dashboards for download and backtest progress |

## Closing Note

The project is best understood as an auditable strategy engine rather than a
single script. Its strength lies not only in the strategy idea itself, but in
the way data preparation, context, entry timing, risk control, scaling, exit
logic, and reporting have been separated into modules that can be reviewed,
tested, and evolved independently.
