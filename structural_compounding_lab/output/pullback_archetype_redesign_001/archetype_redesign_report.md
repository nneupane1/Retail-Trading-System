# Structural Compounding Lab Pullback Archetype Redesign 001

Classification: `continue_research`

## Scope

- research-only
- development windows: `smoke`, `diagnostic_fast`
- holdout preview: `holdout_recent_preview`
- no full-history run
- no stress windows
- no Monte Carlo

## Archetype Comparison (Development)

| Archetype | Candidates | Pass | Pass rate | Normal cost survival | Cost-dominated | Tiny-stop | Missed winner risk | Recommendation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| MICRO_PULLBACK_MOMENTUM | 27 | 1 | 3.704% | 100.000% | 96.296% | 88.889% | 0.000% | continue_refinement |
| BREAKOUT_RETEST_PULLBACK | 10 | 0 | 0.000% | 100.000% | 100.000% | 70.000% | 20.000% | reject_or_redefine |
| EMA_VWAP_RECLAIM_PULLBACK | 72 | 1 | 1.389% | 80.556% | 98.611% | 63.889% | 6.944% | continue_refinement |
| HEALTHY_CONTINUATION_PULLBACK | 32 | 3 | 9.375% | 90.625% | 87.500% | 65.625% | 25.000% | continue_refinement |
| LIQUIDITY_SWEEP_RECLAIM | 101 | 7 | 6.931% | 78.218% | 89.109% | 58.416% | 14.851% | continue_refinement |
| INSIDE_BAR_CONTINUATION | 17 | 0 | 0.000% | 94.118% | 100.000% | 76.471% | 0.000% | reject_or_redefine |
| FAILED_BREAKDOWN_REVERSAL | 1 | 0 | 0.000% | 100.000% | 100.000% | 100.000% | 0.000% | insufficient_sample |
| STRUCTURE_BREAK_DIP | 99 | 0 | 0.000% | 57.576% | 92.929% | 68.687% | 28.283% | reject_or_redefine |

Best archetype: `LIQUIDITY_SWEEP_RECLAIM`
Worst archetype: `STRUCTURE_BREAK_DIP`

## Research Notes

- MACD and Bollinger are classification hints only, not hard gates.
- Pullback buying remains research-only and does not alter runtime entries.
- Full-history confirmation, stress windows, and paper candidate remain blocked.
