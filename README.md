# Retail Trading System

Retail Trading System is a modular research, backtest, and live-paper framework
for Binance futures-style OHLCV trading. The current stack is built around
role-specialized sleeves rather than one monolithic strategy:

- `15m` core for tactical long/short flow
- `12H` standard, moonshot, and rotation sleeves for structural participation
- routed `1H` execution as a short-specialist sleeve with mild bearish-HTF boost
- shared-cap allocator and telemetry layer that decides which opportunities
  deserve risk right now

The project now includes a live-paper cockpit with a FastAPI telemetry backend,
a Next.js dashboard, and a one-command launcher.

## Current Production-Like Stack

- Active sleeves:
  - `15m` core
  - `15m` swing moonshot
  - `12H` standard
  - `12H` moonshot
  - `12H` rotation
  - `1H` routed short sleeve with reversible runtime guard
- Research-only sleeves:
  - `6H` standard
  - `6H` moonshot
- Current universe:
  - selective multi-asset baseline, with broad-universe discovery kept as a
    research feeder rather than a production default

## What The System Is Optimizing

The design goal is portfolio efficiency, not maximum raw trigger count. That
means:

- sleeves are allowed to specialize instead of trading every market condition
- capital competition is treated as real
- weak overlap is filtered out at the allocator layer
- telemetry is first-class, so you can see data flow, signal formation,
  suppression reasons, routing decisions, and live-paper state in real time

## Repository Map

- [`backtest/`](backtest/) for the historical engine, validation helpers, and
  checkpoint logic
- [`common/`](common/) for shared utilities, progress tracking, and dashboard
  telemetry loading
- [`dashboard/`](dashboard/) for the Next.js live cockpit frontend
- [`dashboard_api/`](dashboard_api/) for the FastAPI backend and websocket
  stream
- [`live_sim/`](live_sim/) for the live-paper runner, portfolio loop, logging,
  and telemetry writes
- [`config/`](config/) for strategy, allocator, and branch settings
- [`tests/`](tests/) for unit and integration coverage

## Live Cockpit

The cockpit is designed as a fixed command header plus route-backed lower
modules:

- `Overview`: equity, sleeve stats, daily rhythm, high-level portfolio pulse
- `Market`: candles, trade markers, candidate tape, symbol/timeframe replay
- `Atlas`: multi-asset and multi-timeframe command grid
- `Portfolio`: trades, sleeve leaderboard, open-state context
- `Allocator`: cap pressure, suppression reasons, scarce-risk routing
- `Runtime`: engine heartbeat, data freshness, symbol pipeline, guard state

The dashboard is not a broker or execution engine. It visualizes what the
live-paper stack is actually writing.

## One-Command Launch

Run the full live-paper cockpit from the repo root:

```powershell
python run_live_cockpit.py
```

The launcher is intended to:

- start the live-paper engine
- start or validate the FastAPI telemetry backend
- start or validate the dashboard frontend runtime
- open the cockpit in the default browser
- monitor child-process health
- shut services down cleanly

## Core Commands

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

Install dashboard dependencies:

```powershell
cd dashboard
npm install
```

Start only the dashboard frontend:

```powershell
cd dashboard
npm run dev
```

Start only the telemetry backend:

```powershell
python -m uvicorn dashboard_api.main:app --host 127.0.0.1 --port 8000
```

Run the test suite:

```powershell
python -m unittest discover -s tests -v
```

Build the dashboard for production:

```powershell
cd dashboard
npm run build
```

## Current Research Conclusions

- Naive broad multi-asset expansion hurt performance.
- Selective breadth is useful, but only when symbols earn inclusion.
- `6H` showed standalone edge but did not earn promotion into the routed stack.
- `1H` did earn promotion, but as a specialized short sleeve, not as a
  symmetric execution layer.
- The best `1H` branch is:
  - short-only by default
  - mildly boosted when `12H` is bearish
  - protected by a reversible runtime fallback policy
- Allocator lane pressure mattered more than over-engineering the signal logic.

## Outputs And Telemetry

The live-paper path writes audit artifacts that the dashboard consumes,
including:

- portfolio status
- runtime policy rows
- trade and signal logs
- engine heartbeat
- cycle history
- symbol pipeline status

This makes it possible to monitor the system even when no trade is active.

## Guardrails

- Do not treat research-only sleeves as promoted sleeves without validation.
- Do not assume more symbols or more timeframes automatically improve the
  portfolio.
- Do not optimize individual sleeves in isolation and ignore shared risk.
- Do not use the dashboard as proof of execution; use it as proof of system
  state.

## Status

The current priority is operational polish and controlled live-paper
verification, not adding new strategy complexity.
