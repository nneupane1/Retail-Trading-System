# Structural Frontend Scaffold

The structural lab frontend is intentionally served from the existing dashboard
runtime first, but it is isolated as its own research surface.

## Routes

- `/structural-lab`
- `/structural-lab/overview`
- `/structural-lab/market-replay`
- `/structural-lab/structure-map`
- `/structural-lab/profit-vault`
- `/structural-lab/trade-review`
- `/structural-lab/settings`

## Reused Building Blocks

- candle chart component
- fullscreen chart behavior
- TradingView-style zoom / pan / price-scale handling
- full-browser fullscreen chart theatre
- `Ctrl + wheel` price zoom
- right-axis vertical candle scaling
- `Alt + drag` manual price-scale control
- replay checkpoint banner
- trade marker overlays
- personality labels
- intelligent pullback markers
- pullback-quality and compounding-readiness condition cards
- condition panel
- KPI cards
- signal / decision tape
- dark cockpit styling

## Local Metadata

- `routes.json`: declared route family and read-only scope
- `panel_layout.yaml`: page/panel contract for future UI growth

## Safety

- reads only `structural_compounding_lab/output/`
- does not mutate paper/live state
- does not change current `/paper`, `/backtest`, or `/live` behavior
- does not depend on the active Phase 2 capital-lane experiment

## Structural Replay Focus

The market-replay route is chart-first. The chart stays dominant, while vault state,
setup context, cooldown events, and convexity events are pushed below it rather than
competing with it above the fold.
