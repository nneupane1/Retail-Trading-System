# Capital-Expression Refactor Report for the Retail Trading System

## 1. Executive Summary

The current trading system has reached an important stage: it is no longer a loose research experiment. It now has a validated production gate, true trailing holdout logic, paper-only readiness enforcement, clean forward-paper startup, dashboard truth alignment, soak reporting, and operational safety controls. The system has shown a strong full-history result, but the trailing 12-month unseen holdout passed only narrowly. This means the architecture has real historical edge, but the recent edge is not yet strong enough to justify live capital or aggressive scaling. Therefore, the next major project phase should not be random strategy invention. It should be a disciplined **capital-expression refactor**: redesign how the system allocates, protects, recycles, compounds, and concentrates capital around the strongest proven edges.

The million goal requires a very different standard from merely being profitable. Turning €20k into €1M means a 50x return. Over five years, that implies roughly more than doubling the account annually. A system that makes 1% to 15% per year with low drawdown may be valuable, but it will not reach the stated goal. Therefore, the refactor must answer one question: **how do we safely allow the best edges to carry much more of the capital while preventing weak, noisy, or regime-mismatched trades from consuming risk budget?**

The Step 1 validation showed an important split. Full-history performance was strong, especially from the 12H sleeves and selected structural trades. But the recent trailing holdout was thin, with core and swing weak while HTF sleeves and H1 carried the small positive result. This tells us that the system’s current edge is not evenly distributed. It is concentrated by sleeve, score bucket, market regime, trade lifecycle, and possibly a small number of large structural winners. The capital refactor must therefore make the system less democratic. It must stop treating all valid trades as equal and instead build a clear hierarchy: **structural HTF winners first, clean 0.9–1.0 bucket second, recent-health-confirmed tactical trades third, weak sleeves last or disabled.**

The key refactor is not “take more risk everywhere.” That would likely destroy the system. The correct refactor is: **increase capital only where the evidence says the edge is repeatable, persistent, and structurally justified; reduce capital where trades are noisy, low-quality, or merely active.** In other words, the path to €1M is not more trades. It is better capital placement.

---

## 2. Current State After Validation

The current system is classified as **paper-only**. Operationally, this is now clean. SSL verification is enabled, real-money startup fails closed, readiness is centralized, the dashboard is read-only, and paper runtime starts from the validated boundary without importing backtest or holdout trades. This means the remaining blocker is no longer infrastructure. The remaining blocker is **forward evidence and capital quality**.

The full-history routed stack showed meaningful economic performance, with the account growing from €20k to roughly €56k. That is historically promising. However, the trailing 12-month holdout barely passed, producing less than 1% return with a profit factor close to breakeven. This is the most important recent-reality signal. It means the system survived, but it did not express enough edge in the most recent unseen period.

This creates the correct interpretation: the system is not useless, but it is not yet a wealth-compounding engine. The current version is a validated baseline. The next phase must turn it from a baseline into a capital-efficient engine.

---

## 3. Why the Million Goal Requires Capital Refactor

The million goal cannot be reached by simply running the current system unchanged. A system that barely passes the latest 12-month holdout is not yet expressing enough recent edge. Even if full-history results are strong, the latest holdout says that recent market conditions may have diluted the edge. Therefore, scaling the current version blindly would be dangerous.

To reach €1M from €20k, the system needs a path that combines:

1. Higher average capital deployment into high-quality trades.
2. Better winner retention.
3. Better pyramiding only after proof.
4. Lower capital leakage into weak sleeves.
5. Faster recycling of capital from dead trades.
6. Regime-aware risk expansion and contraction.
7. Strict drawdown control so the system survives long enough to compound.
8. A clear hierarchy between “flow trades” and “wealth trades.”

The current system already has some of this architecture: core, H1, 12H standard, 12H moonshot, 12H rotation, allocator logic, health filters, score buckets, and lifecycle concepts. But the capital allocation is still too flat and not yet ruthlessly aligned with edge quality. The refactor must make capital behave like a portfolio manager, not like a signal executor.

---

## 4. Main Diagnosis: The System Has Edge Concentration, Not Uniform Edge

The evidence points to a strong concentration pattern. The 12H sleeves, especially rotation and moonshot structures, are the likely wealth engine. Core generates many trades and can contribute, but its edge is thinner and more regime-sensitive. H1 has value as a secondary tactical lane, especially with the short override. Swing moonshot has repeatedly appeared weak and should not receive meaningful capital unless paper evidence proves otherwise. The 0.9–1.0 score bucket has shown much stronger behavior than lower buckets, while 0.8–0.9 often leaks capital despite appearing close to valid.

This means the system should not allocate capital merely because a trade is valid. It should allocate capital according to a hierarchy:

**Tier 1: Structural wealth trades**

* 12H moonshot
* 12H rotation
* 12H standard when aligned with regime and score
* Large HTF continuation structures
* Trades with validated lifecycle proof and enough room to run

**Tier 2: Tactical compounding trades**

* High-score core trades
* H1 execution trades when runtime health is positive
* 0.9–1.0 trades with recent strategy health confirmation

**Tier 3: Low-conviction / capital-light trades**

* 0.8–0.9 bucket trades
* core trades during weak recent performance
* H1 when below runtime health threshold
* swing moonshot until redesigned or proven

**Tier 4: Disabled or observation-only**

* 6H sleeves currently disabled
* weak swing variants
* any sleeve with poor paper evidence
* any bucket with negative recent expectancy

The capital refactor should encode this hierarchy directly into the allocator.

---

## 5. Refactor Theme 1: Capital Lanes

The system should separate capital into explicit lanes instead of letting all strategies compete equally for one shared risk pool. The current shared risk cap can block good trades because noisy tactical trades may consume capital before structural opportunities appear. This is especially dangerous if the 12H sleeves are the actual wealth engine.

The proposed lanes are:

**Lane A: Core Flow Lane**
Purpose: frequent tactical trades, small-to-moderate risk, liquidity generation, regime sensing.
Capital: limited.
Risk: modest.
Scaling: only for 0.9–1.0 and recent-health-positive core setups.
Role: keep account active, but not dominate risk.

**Lane B: H1 Tactical Short/Transition Lane**
Purpose: catch directional short opportunities and medium-frequency tactical trades.
Capital: smaller than HTF lane, larger than experimental sleeves only if paper confirms.
Risk: guarded.
Scaling: only if H1 runtime policy passes profit factor and average R thresholds.
Role: hedge-like tactical contributor, not primary wealth engine.

**Lane C: 12H Structural Wealth Lane**
Purpose: carry the account through large structural moves.
Capital: highest priority.
Risk: allowed to expand when structure, score, regime, and lifecycle proof align.
Scaling: staged entry, validation, add-on, and trailing logic.
Role: primary million-goal engine.

**Lane D: Experimental / Disabled Lane**
Purpose: observation only.
Capital: zero or tiny.
Includes swing moonshot until proven, 6H disabled sleeves, any low-confidence variant.
Role: research data collection, not compounding.

This lane separation prevents the worst problem: low-quality tactical activity starving high-quality structural trades.

---

## 6. Refactor Theme 2: Strategy-Level Risk Budgets

Each sleeve needs a dynamic risk budget, not a fixed or equal budget. Risk should expand only when a sleeve proves itself in recent paper evidence and validation evidence. Risk should contract quickly when recent performance deteriorates.

A suggested risk hierarchy:

**12H rotation**

* Strong candidate for increased allocation.
* Should receive priority under shared risk conflicts.
* Risk can scale when recent 12H rotation performance is positive and no stale runtime warning exists.

**12H moonshot**

* Potentially highest upside.
* Should not fire often, but when it fires in high-quality conditions it should be allowed enough room to matter.
* Needs lifecycle confirmation before add-ons.

**12H standard**

* Stable structural contributor.
* Can receive moderate capital.
* Should be used as structural base layer.

**Core**

* Should be restricted to high-quality buckets.
* Avoid allowing core to dominate shared risk budget.
* Core 0.8–0.9 should be heavily reduced or disabled unless paper proves otherwise.

**H1 execution**

* Keep active, but risk should depend on runtime policy.
* If H1 falls below minimum PF or avg_R, it should remain small or fallback-only.
* H1 short override should stay, but not become uncontrolled.

**Swing moonshot**

* Current evidence is weak.
* Keep health-gated or reduce to observation-only.
* Do not allocate meaningful capital until it shows forward paper improvement.

The key principle: **risk follows evidence, not enthusiasm.**

---

## 7. Refactor Theme 3: Score-Bucket Capital Multipliers

The system should make score bucket quality matter more directly. The 0.9–1.0 bucket has repeatedly been the strongest quality zone. Lower buckets often dilute edge.

A starting capital policy could be:

**0.9–1.0**

* Full risk eligibility.
* Can receive capital multipliers if strategy health is positive.
* HTF 0.9–1.0 gets priority over core 0.9–1.0 during shared risk conflicts.

**0.8–0.9**

* Reduced risk by default.
* Allowed only for specific sleeves where paper evidence supports it.
* If recent bucket PF is below 1.05 or 1.10, block or reduce heavily.

**0.7–0.8**

* Disabled by default.
* Only allowed for special HTF structural exceptions if explicitly proven.
* No normal tactical trades.

**0.6–0.7**

* Disabled except research.
* Too little evidence and too dangerous for capital expression.

But score alone is not enough. The correct formula is:

**capital multiplier = score bucket multiplier × strategy health multiplier × regime multiplier × lifecycle state multiplier × portfolio concentration multiplier**

This prevents blind scaling of all high-score trades.

---

## 8. Refactor Theme 4: Lifecycle State Machine

The system needs a stronger lifecycle state machine for open positions. The million goal depends on letting winners become meaningful while cutting dead positions early. Every position should move through states:

**candidate**
A valid signal exists, but no capital committed yet.

**probe**
Small initial position. Used to test whether the market accepts the trade idea.

**validated**
Price action confirms the trade after entry. Stop can be improved or position becomes eligible for holding.

**promoted**
Trade has moved enough in favor, structure remains intact, and capital can be increased.

**add-on eligible**
A continuation opportunity appears after proof. Add-on is allowed only if the stop-aware risk remains controlled.

**runner**
The trade has paid for itself and should be trailed for larger R.

**moonshot**
The trade is now a rare structural winner candidate. It should be protected from premature exit.

**de-risk**
Position is losing structure or regime support. Reduce or exit.

**exit**
Position is closed.

The current system already has some lifecycle concepts, but the refactor should make lifecycle the center of capital decisions. The system should not ask only “should I enter?” It should constantly ask: “Should this trade receive more capital, less capital, or more time?”

---

## 9. Refactor Theme 5: Add-On and Pyramiding After Proof

To reach the million goal, the system cannot rely only on first entries. It must scale into rare winners. But pyramiding before proof is dangerous. Therefore, add-ons should be allowed only after objective proof.

Suggested add-on rules:

A trade becomes add-on eligible only when:

* It is already profitable.
* The original stop or structural stop can be improved.
* Current open risk after add-on remains within allowed portfolio risk.
* Trend structure remains valid.
* Score/regime/HTF confirmation remains positive.
* The add-on does not increase total account drawdown risk beyond limit.
* The trade belongs to an approved capital lane.

The best candidates for add-ons are likely:

* 12H moonshot trades.
* 12H rotation trades.
* 12H standard trades that transition into strong trend continuation.
* Selected core trades only if they become HTF-aligned runners.

The worst candidates for add-ons are:

* Low-score tactical trades.
* Mean-reversion-like entries.
* Weak swing trades.
* Trades in low-liquidity or noisy regimes.
* Trades already blocked by recent health.

The purpose of pyramiding is not to increase trade count. It is to make the best few trades matter.

---

## 10. Refactor Theme 6: Capital Recycling

Capital recycling means freeing capital from positions that are no longer worth holding and moving it into better opportunities. Without this, the system can become capital-locked in mediocre trades while missing structural winners.

The refactor should track:

* How long capital has been locked.
* Whether the trade is progressing.
* Whether unrealized R is improving or decaying.
* Whether another candidate has higher expected value.
* Whether the current position is blocking a better same-symbol or same-lane opportunity.
* Whether the trade still belongs to its original thesis.

A position should be recycled if:

* It is flat for too long.
* It loses structure.
* It blocks a higher-ranked HTF opportunity.
* It fails validation after probe entry.
* Its opportunity cost exceeds its remaining expectancy.

This requires an **opportunity-cost engine**. The allocator should not just ask whether a new trade fits risk caps. It should ask whether existing capital is being used well.

---

## 11. Refactor Theme 7: Rejection Shadow Book

The current system already records rejection reasons such as shared risk cap, score bucket filtering, direction cap, asset cap, same-symbol cap, strategy sleeve cap, and allocator rank filtering. The next level is a **rejection shadow book**.

Every rejected trade should be tracked as if it were paper-traded in a shadow ledger. This allows the system to answer:

* Which rejected trades would have made money?
* Which rejection reason blocks the most future profit?
* Did shared risk cap block winners or save losses?
* Did direction cap block structural HTF winners?
* Did core trades consume capital that should have gone to 12H?
* Are rejected 0.8–0.9 trades actually bad, or are some subsets valuable?
* Are same-symbol conflicts hurting or helping?

This is critical for capital expression. If the system’s biggest winners were rejected due to capital caps, then the issue is not signal quality; it is allocator priority.

The shadow book should include:

* signal timestamp,
* symbol,
* strategy,
* side,
* score bucket,
* rejection reason,
* hypothetical entry,
* hypothetical stop,
* hypothetical exit after standard rules,
* hypothetical R,
* hypothetical PnL,
* whether it would have beaten the accepted trade.

This will identify the most valuable allocator refactors.

---

## 12. Refactor Theme 8: Winner Forensics

The system appears convex: a small number of large trades may carry a large portion of total profit. This is normal for trend/moonshot systems, but it must be studied carefully. The refactor should include a top-winner forensic module.

For the top 20 or top 50 historical winners, extract:

* symbol,
* strategy,
* side,
* score bucket,
* date,
* market regime,
* HTF trend state,
* holding time,
* maximum favorable excursion,
* maximum adverse excursion,
* entry quality,
* add-on opportunities,
* exit reason,
* whether the system exited too early,
* whether capital was too small,
* whether another sleeve also signaled,
* whether rejected sister trades existed.

The goal is to understand what the true wealth trades look like before they become obvious. If top winners share common features, those features should drive capital priority.

The million goal depends on capturing and sizing these winners. If the system repeatedly enters them too small or exits too early, it will remain modest even with good signals.

---

## 13. Refactor Theme 9: Drawdown-Aware Scaling

Aggressive compounding without drawdown control will eventually fail. The capital refactor must include risk bands based on equity curve health.

Suggested risk bands:

**Green band**

* Equity above moving equity high or drawdown below small threshold.
* System health positive.
* HTF sleeves performing.
* Allow normal or expanded risk.

**Yellow band**

* Moderate drawdown.
* Reduce core and H1 risk.
* Keep only strongest HTF setups.
* Disable lower buckets.

**Red band**

* Drawdown exceeds strict threshold.
* New entries reduced or paused.
* Only protective exits and very rare A+ setups allowed.
* No add-ons.
* No pyramiding.

**Recovery band**

* After drawdown stabilizes, slowly re-enable risk.
* Require recent health confirmation before returning to green.

This protects the system from the exact danger of chasing the million goal too aggressively.

---

## 14. Refactor Theme 10: Regime-Aware Capital

The system must know when its edge is likely active. Crypto regimes change dramatically: trending bull, choppy bull, sharp bear, sideways volatility compression, liquidation cascades, post-news expansion, and slow grind environments. A strategy that works in one regime may leak in another.

The capital refactor should include regime multipliers:

* HTF trend alignment.
* Volatility expansion or compression.
* BTC dominance / broad market alignment if available.
* 12H/1D trend state.
* Correlation across current_9 symbols.
* Market-wide risk-on/risk-off behavior.
* Funding or derivatives context if added later.
* Session/liquidity context if relevant.

A simple starting rule:

* Expand HTF risk in strong aligned trend regimes.
* Reduce core tactical risk in choppy regimes.
* Reduce all risk during unstable high-correlation drawdowns.
* Allow H1 short lane more room during bearish transition regimes.
* Do not allow swing moonshot unless regime supports it.

The million goal requires being aggressive only when the market deserves aggression.

---

## 15. Refactor Theme 11: Portfolio Heat and Correlation Control

Because the system trades multiple crypto pairs, positions are not independent. BTC, ETH, SOL, AVAX, BNB, LINK, XRP, TRX, and AAVE can become highly correlated during market stress. The system must manage portfolio heat by correlation and direction.

The refactor should track:

* total open risk,
* risk by side,
* risk by symbol,
* risk by sector-like group,
* risk by capital lane,
* risk by strategy,
* BTC/ETH beta exposure,
* correlated long exposure,
* correlated short exposure.

If multiple long trades are effectively the same market bet, capital should be reduced or concentrated into the best-ranked candidate.

Capital concentration should be intentional:

* In normal conditions, diversify across top opportunities.
* In strong trend conditions, concentrate in the strongest structural setups.
* In stress conditions, reduce all correlated exposure.

This prevents the system from thinking it has five trades when it really has one trade repeated five times.

---

## 16. Refactor Theme 12: Separate Return Engine From Safety Engine

The system should clearly separate two questions:

1. **Where is edge?**
2. **How much capital should express that edge?**

The current architecture has signals, scores, sleeves, and allocator rules. The refactor should make capital expression its own layer. That layer should receive candidate trades and decide:

* reject,
* probe,
* normal entry,
* reduced entry,
* promoted entry,
* add-on,
* hold,
* de-risk,
* exit.

This makes capital allocation explicit, testable, and auditable.

The capital engine should not modify signals. It should decide how much to trust them.

---

## 17. Proposed New Modules

The following modules should be considered during the capital refactor:

### 17.1 `capital_lanes.py`

Defines capital lanes, budgets, lane priorities, and max exposure per lane.

### 17.2 `risk_bands.py`

Implements green/yellow/red/recovery risk states based on drawdown and system health.

### 17.3 `lifecycle_state_machine.py`

Manages probe, validated, promoted, add-on eligible, runner, moonshot, de-risk, and exit states.

### 17.4 `opportunity_cost.py`

Scores whether existing positions deserve capital compared with new candidates.

### 17.5 `shadow_rejection_book.py`

Tracks rejected trades and their hypothetical outcomes.

### 17.6 `winner_forensics.py`

Analyzes top winners, missed winners, and early exits.

### 17.7 `capital_recycling.py`

Frees capital from dead trades and reallocates to stronger candidates.

### 17.8 `regime_capital_multiplier.py`

Applies regime-based risk expansion or contraction.

### 17.9 `portfolio_heat.py`

Tracks correlated exposure and account-level risk.

### 17.10 `promotion_review.py`

Evaluates whether paper evidence supports increasing capital allocation or keeping paper-only.

These should be introduced gradually, not all at once.

---

## 18. Refactor Priority Order

The capital refactor should be done in a strict order. Do not start with pyramiding. Do not start with new strategies. Start with diagnostics and allocator truth.

### Phase 1: Diagnostics Before Behavior Change

Build:

* shadow rejection book,
* top-winner forensics,
* capital-blocked-winner analysis,
* sleeve/bucket capital efficiency report,
* opportunity-cost report.

Goal: identify where money is being lost, blocked, or under-allocated.

### Phase 2: Capital Lane Separation

Implement:

* core flow lane,
* H1 tactical lane,
* 12H structural lane,
* experimental lane.

Goal: prevent core noise from starving structural HTF trades.

### Phase 3: Score/Bucket Risk Multipliers

Implement:

* strong 0.9–1.0 priority,
* reduced or disabled 0.8–0.9 leakage,
* block low buckets except proven exceptions.

Goal: stop weak buckets consuming capital.

### Phase 4: Lifecycle State Machine

Implement:

* probe,
* validation,
* promotion,
* add-on eligibility,
* runner state,
* de-risk state.

Goal: capital increases only after proof.

### Phase 5: Add-On and Pyramiding

Implement only after lifecycle works.
Goal: allow rare winners to become large enough to matter.

### Phase 6: Capital Recycling

Implement opportunity-cost exits and reallocation.
Goal: capital does not remain trapped in mediocre positions.

### Phase 7: Regime-Aware Scaling

Expand or contract risk based on market state.
Goal: be aggressive only in favorable regimes.

### Phase 8: Full Gate + Holdout + Paper Soak

Every meaningful behavior change must go through:

* targeted tests,
* scenario replay,
* full production gate,
* trailing 12-month holdout,
* clean paper start,
* paper soak.

Goal: no untested capital logic reaches live.

---

## 19. Specific Refactor Ideas Based on Current Evidence

### 19.1 Reduce Core Capital During Weak Regimes

Core is useful, but it can be noisy. In the trailing holdout, core was weak. Core should not receive unlimited risk just because it has many signals. Reduce core risk when:

* recent core PF < threshold,
* core 0.8–0.9 is negative,
* HTF opportunities are competing for capital,
* market is choppy.

### 19.2 Prioritize 12H Rotation

12H rotation has shown strong structural contribution. It should receive higher priority under allocator conflicts. If a 12H rotation trade and a core trade compete for shared risk, the 12H trade should usually win.

### 19.3 Let 12H Moonshot Breathe

12H moonshot is a potential million-goal sleeve. It should not be overtraded, but when it appears with high score and regime support, it must receive enough capital and time. The refactor should focus on avoiding premature exit and enabling add-ons only after proof.

### 19.4 Keep H1 as Tactical Support

H1 contributes but should not become the main engine. Keep the short override, but risk should remain conditional on runtime health.

### 19.5 Suppress Swing Moonshot

Swing moonshot has been weak. Keep it health-gated or observation-only until forward paper proves otherwise.

### 19.6 Control 0.8–0.9 Leakage

The 0.8–0.9 bucket has repeatedly shown leakage. It should be reduced, blocked, or restricted to only the sleeves where evidence supports it.

### 19.7 Study Capital-Cap Rejections

Shared risk cap and sleeve caps may be blocking good trades. The shadow book must reveal whether these caps saved money or blocked winners.

### 19.8 Focus on Top Winner Capture

If top trades carry most of the profit, then the system must specialize in identifying, sizing, and holding those trades.

---

## 20. Million-Goal Capital Model

A realistic million-path model is not linear. It likely requires stages.

### Stage 1: Proof Stage

Capital: paper only, then tiny live later if allowed.
Goal: prove runtime correctness and forward edge.
No scaling.

### Stage 2: Stability Stage

Capital: small real allocation only after paper evidence and readiness approval.
Goal: verify slippage, execution, order handling, psychological stability, and live-paper parity.
Risk: very small.

### Stage 3: Compounding Stage

Capital: gradually increased.
Goal: allow validated HTF sleeves to carry more risk.
Risk: still bounded by drawdown bands.

### Stage 4: Convexity Stage

Capital: add-ons and pyramiding after proof.
Goal: allow top winners to create account jumps.
Risk: controlled, not reckless.

### Stage 5: Portfolio Scaling Stage

Capital: larger account, possibly more instruments or venues only after evidence.
Goal: maintain edge while increasing capacity.

The system should not jump from paper to Stage 4. That would be gambling.

---

## 21. What Must Not Be Done

The following must be explicitly avoided:

* Do not add new symbols yet.
* Do not add new sleeves yet.
* Do not enable 6H just because it exists.
* Do not optimize parameters against full-history results.
* Do not increase risk globally.
* Do not scale 0.8–0.9 trades blindly.
* Do not let core consume all capital.
* Do not start real money because the full-history result looks good.
* Do not ignore the thin holdout.
* Do not refactor everything at once.
* Do not confuse backtest equity with live tradability.
* Do not pursue €1M by increasing risk without edge confirmation.

The capital refactor must be surgical, not emotional.

---

## 22. Testing Plan for Capital Refactor

Every capital change must be tested through a pyramid:

### 22.1 Unit Tests

Test lane budgets, risk multipliers, lifecycle transitions, add-on rules, and rejection shadow book.

### 22.2 Small Scenario Tests

Run a short period with known trades and verify expected allocator behavior.

### 22.3 Replay Tests

Replay cached decisions where possible to test allocator changes quickly.

### 22.4 Full Production Gate

Run full-history and trailing holdout only for serious candidates.

### 22.5 Monte Carlo

Test trade-order sensitivity, drawdown distribution, probability of loss, probability of doubling, and tail risk.

### 22.6 Paper Soak

Run forward paper again after any major capital change.

No capital refactor should be considered complete without holdout and paper evidence.

---

## 23. Success Metrics

The capital refactor should not be judged only by final equity. It should be judged by:

* Full-history return improves without extreme drawdown.
* Trailing holdout return improves meaningfully.
* Profit factor improves or remains stable.
* Max drawdown remains acceptable.
* 12H sleeves receive capital when appropriate.
* Weak core regimes consume less capital.
* 0.8–0.9 leakage reduces.
* Shadow rejected winners decrease.
* Top winners receive larger effective exposure.
* Add-ons improve return without unacceptable drawdown.
* Monte Carlo probability of severe loss remains controlled.
* Monte Carlo probability of doubling improves.
* Paper-soak evidence confirms runtime behavior.

The most important near-term metric is not €1M. It is whether the trailing holdout improves from barely positive to meaningfully positive without exploding drawdown.

---

## 24. First Concrete Capital-Refactor Sprint

The first capital-refactor sprint should not change live behavior immediately. It should be diagnostic.

Recommended Sprint 1:

1. Build `shadow_rejection_book.py`.
2. Build capital-blocked-winner analysis.
3. Build top-50 winner forensic report.
4. Build strategy × bucket × regime capital efficiency report.
5. Build opportunity-cost report for open/held positions.
6. Add reports to dashboard as read-only diagnostics.
7. Run on full-history and trailing holdout artifacts.
8. Identify exactly which capital rules should change.

Deliverables:

* `rejection_shadow_book.csv`
* `capital_blocked_winners.csv`
* `top_winner_forensics.csv`
* `strategy_bucket_capital_efficiency.json`
* `opportunity_cost_report.json`
* recommendation report for capital lane changes

Only after this diagnostic sprint should behavior-changing allocator refactors begin.

---

## 25. Final Recommendation

The correct next major development phase after paper soak is **not a new strategy**. It is a capital-expression refactor. The system already has enough moving parts. The missing piece is not more complexity; it is better capital intelligence.

The million goal requires the system to become much more selective and much more aggressive only when conditions deserve it. That means:

* HTF structural trades must get priority.
* Weak buckets must stop leaking capital.
* Core must not starve 12H wealth trades.
* Winners must be held and scaled after proof.
* Dead trades must release capital faster.
* Rejections must be audited as shadow trades.
* Top winners must be studied and captured better.
* Risk must expand and contract with regime and drawdown.
* Every refactor must pass full gate, holdout, Monte Carlo, and paper soak.

This is the serious path. It does not guarantee €1M, but it gives the system a rational chance. The current baseline proves the project is worth continuing. The capital refactor is the bridge between a profitable research system and a possible wealth-compounding engine.
