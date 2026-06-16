# Structural Compounding Lab Architecture

This lab is intentionally split into the same economic layers as the main project,
but with a different research thesis.

## Layers

1. `data/`
Local history loading and HTF resampling only. No live mutation.

2. `indicators/`
EMA, ATR, and VWAP wrappers reused from the main project so indicator math stays consistent.

3. `market_structure/`
Support/resistance, pivots, touch strength, and liquidity event detection.

4. `context/`
HTF bias, trend regime classification, and danger-state interpretation.

5. `entry/`
Setup detection, scoring, and trade-plan construction.

6. `capital/`
Base-capital model, profit vault, pyramiding rules, and risk budgeting.

7. `exit/`
Trailing reward capture, danger exits, and cooldown logic.

8. `backtest/`
Single-position research engine that writes a complete artifact bundle.

9. `frontend/`
Read-only route contract for the dashboard shell under `/structural-lab`.

## Safety

- No live orders
- No paper-runtime mutation
- No allocator integration with the active system
- No real-money pathway
- No dependency on the running Phase 2 replay
