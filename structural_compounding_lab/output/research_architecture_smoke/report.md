# Structural Compounding Lab Report

## Executive Summary

- Symbol: `BTCUSDT`
- Execution timeframe: `15m`
- Current equity: `20000.00`
- Locked profit: `0.00`
- Active trading capital: `20000.00`
- Trade count: `0`
- Win rate: `0.00%`
- Profit factor: `0.00`
- Average R: `0.00`
- Max drawdown: `0.00%`

## Run Window

- Config analysis start: `2026-01-01`
- Config analysis end: `2026-01-01`
- Loaded execution start: `None`
- Loaded execution end: `None`
- Source CSV: `C:\Users\v25946b\OneDrive - Iveco Group\Documents\Retail-Trading-System\structural_compounding_lab\tests\fixtures\btcusdt_structural_fixture_1m.csv`

## Strategy Logic

- structural levels are derived from pivots, rolling range anchors, and prior-session references
- liquidity context comes from equal levels, sweeps, failed breaks, and reclaim logic
- setup acceptance requires economically viable risk/reward rather than pattern presence alone
- convexity adjusts risk and add-on budget instead of blindly pyramiding every winner
- danger-aware cooldown can clear early only for strong aligned setups

## Model Windows

- Structure window: `64` bars
- Liquidity window: `48` bars
- Setup window: `32` bars
- Recent liquidity horizon: `8` bars

## Artifact Counts

- Setups logged: `0`
- Structural levels logged: `0`
- Liquidity events logged: `0`
- Add-on events: `0`
- Profit locks: `0`
- Cooldown events: `0`

## Settings Snapshot

- Confirmation timeframes: `['1h', '4h']`
- Base capital: `20000.0`
- Risk per trade pct: `0.01`
- Minimum RR: `1.05`
- Convexity enabled: `True`
- Profit vault enabled: `True`

## Research Layer

- momentum personality is research-only and never a hard gate by default
- intelligent pullback accumulation compares original entry geometry against refined pullback geometry
- compounding readiness is diagnostic only and does not mutate pyramiding or exits
- execution cost sensitivity remains research-only and does not alter live/paper behavior
