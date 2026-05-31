"""Coordinates strategy context, entries, management, exits, account updates, and logging."""

import time

from common.debug import debug_print as print
from config import AppConfig
from simulation.account import Account
from simulation.trade import Trade

from bias.bias_detector import BiasDetector
from regime.regime_detector import RegimeDetector
from entry.scoring import ScoreEngine
from entry.entry_engine import EntryEngine
from entry.exploration_engine import ExplorationEngine

from position.sizing import PositionSizer
from pyramiding.pyramiding_engine import PyramidingEngine
from sniffing.trend_sniffer import TrendSniffer
from exit.exit_engine import ExitEngine


class Simulator:
    """
    Coordinates one candle of strategy work at a time.

    The simulator is intentionally thin: it asks each configured module for one
    decision, updates trade/account state, and delegates persistence to loggers.
    Keeping orchestration here makes the strategy path auditable from context
    detection through entry, management, exit, and equity logging.
    """

    def __init__(
        self,
        initial_equity=None,
        risk_per_trade=None,
        trade_logger=None,
        equity_logger=None,
        entry_engine=None,
        score_engine=None,
        bias_detector=None,
        regime_detector=None,
        pyramiding_engine=None,
        trend_sniffer=None,
        exit_engine=None,
        position_sizer=None,
        exploration_engine=None,
        opportunity_logger=None,
        config=None
    ):

        print("\nInitializing Simulator...")

        self.config = config or AppConfig.load()
        getter = getattr(self.config, "get", None)
        if callable(getter):
            enabled_sides = getter(
                "strategy",
                "directional",
                "enabled_sides",
                default=["long"],
            )
        else:
            enabled_sides = ["long"]
        self.enabled_sides = {str(side).lower() for side in (enabled_sides or ["long"])}
        self.risk_per_trade = (
            risk_per_trade
            if risk_per_trade is not None
            else self.config.require("account", "risk_per_trade")
        )
        if callable(getter):
            risk_per_trade_by_side = getter(
                "account",
                "risk_per_trade_by_side",
                default={},
            ) or {}
        else:
            risk_per_trade_by_side = {}
        self.risk_per_trade_by_side = {
            str(side).lower(): float(value)
            for side, value in risk_per_trade_by_side.items()
        }

        self.account = Account(
            initial_equity=initial_equity,
            config=self.config
        )

        self.current_trade = None
        self.base_size = 0
        self.level = 0
        self.trade_logger = trade_logger
        self.equity_logger = equity_logger
        self.entry_engine = entry_engine or EntryEngine(config=self.config)
        self.score_engine = score_engine or ScoreEngine(config=self.config)
        self.bias_detector = bias_detector or BiasDetector(config=self.config)
        self.regime_detector = regime_detector or RegimeDetector(config=self.config)
        self.pyramiding_engine = pyramiding_engine or PyramidingEngine(config=self.config)
        self.trend_sniffer = trend_sniffer or TrendSniffer(config=self.config)
        self.exit_engine = exit_engine or ExitEngine()
        self.position_sizer = position_sizer or PositionSizer()
        self.exploration_engine = exploration_engine or ExplorationEngine(config=self.config)
        self.opportunity_logger = opportunity_logger
        weighted_mode_getter = getattr(self.entry_engine, "is_weighted_mode", None)
        self.weighted_entry_mode = bool(weighted_mode_getter()) if callable(weighted_mode_getter) else False
        self._opportunity_sequence = 0

    @staticmethod
    def _choose_direction(candidates):
        candidates = [candidate for candidate in (candidates or []) if candidate is not None]
        if not candidates:
            return None

        best_priority = max(int(candidate.get("entry_priority", 0)) for candidate in candidates)
        priority_winners = [
            candidate for candidate in candidates
            if int(candidate.get("entry_priority", 0)) == best_priority
        ]

        best_score = max(
            float(candidate.get("selection_value", candidate.get("score", 0)))
            for candidate in priority_winners
        )
        score_winners = [
            candidate for candidate in priority_winners
            if float(candidate.get("selection_value", candidate.get("score", 0))) == best_score
        ]

        if len(score_winners) == 1:
            return score_winners[0]

        winning_sides = {candidate.get("side") for candidate in score_winners}
        if len(winning_sides) > 1:
            return None

        return score_winners[0]

    def _log_opportunity(self, payload):
        if self.opportunity_logger is None or not payload:
            return

        log_method = getattr(self.opportunity_logger, "log_opportunity", None)
        if callable(log_method):
            log_method(payload)

    def _assign_opportunity_id(self, payload):
        if not payload:
            return None

        existing = payload.get("opportunity_id")
        if existing:
            return existing

        self._opportunity_sequence += 1
        timestamp = payload.get("timestamp")
        if hasattr(timestamp, "isoformat"):
            timestamp_text = timestamp.isoformat()
        else:
            timestamp_text = str(timestamp)
        safe_timestamp = (
            timestamp_text.replace(" ", "T")
            .replace(":", "-")
            .replace("/", "-")
        )
        opportunity_id = (
            f"opp_{safe_timestamp}_{payload.get('side', 'na')}_"
            f"{payload.get('signal_family', 'signal')}_{self._opportunity_sequence:06d}"
        )
        payload["opportunity_id"] = opportunity_id

        candidate = payload.get("candidate")
        if isinstance(candidate, dict):
            candidate["opportunity_id"] = opportunity_id
            trade = candidate.get("trade")
            if trade is not None and hasattr(trade, "annotate_opportunity"):
                trade.annotate_opportunity(opportunity_id)
            elif trade is not None:
                setattr(trade, "opportunity_id", opportunity_id)

        return opportunity_id

    @staticmethod
    def _enrich_opportunity_payload(payload, bias_snapshot=None, regime_snapshot=None):
        if not payload:
            return payload
        if bias_snapshot:
            payload["bias_snapshot"] = dict(bias_snapshot)
            payload["bias_directional_strength"] = bias_snapshot.get(
                "directional_strength"
            )
            payload["bias_price_vs_ema_ratio"] = bias_snapshot.get(
                "price_vs_ema_ratio"
            )
            payload["bias_ema_slope"] = bias_snapshot.get("ema_slope")
        if regime_snapshot:
            payload["regime_snapshot"] = dict(regime_snapshot)
            payload["regime_max_score"] = regime_snapshot.get("max_score")
            payload["regime_normalized_strength"] = regime_snapshot.get(
                "normalized_strength"
            )
            payload["regime_macro_aligned"] = regime_snapshot.get("macro_aligned")
            payload["regime_slope_aligned"] = regime_snapshot.get("slope_aligned")
            payload["regime_trend_aligned"] = regime_snapshot.get("trend_aligned")
        return payload

    def _close_current_trade(self, row, reason=None, exit_price=None):
        trade = self.current_trade

        if reason:
            print(f"\nEXITING TRADE ({reason})")

        if hasattr(trade, "annotate_exit") and callable(trade.annotate_exit):
            trade.annotate_exit(reason=reason)
        else:
            trade.exit_reason = reason

        trade.close(row, exit_price=exit_price)
        self.account.update(trade)

        if self.trade_logger:
            self.trade_logger.log_trade(trade)

        self.current_trade = None
        self.base_size = 0
        self.level = 0

    def _regime_allows_entry(self, regime_score):
        if isinstance(regime_score, dict):
            if "allows_entries" in regime_score:
                return bool(regime_score["allows_entries"])
            regime_score = regime_score.get("raw_score")
        if regime_score is None:
            return False
        allows_entries = getattr(self.regime_detector, "allows_entries", None)
        if callable(allows_entries):
            return allows_entries(regime_score)
        return True

    def _regime_classification(self, regime_score):
        if isinstance(regime_score, dict):
            if regime_score.get("class") is not None:
                return regime_score.get("class")
            regime_score = regime_score.get("raw_score")
        classify = getattr(self.regime_detector, "classify", None)
        if callable(classify):
            return classify(regime_score)
        return None

    def _compute_bias_snapshot(self, df_1h):
        getter = getattr(self.bias_detector, "get_bias_snapshot", None)
        if callable(getter):
            snapshot = getter(df_1h)
            if isinstance(snapshot, dict):
                return snapshot
        label = self.bias_detector.get_bias(df_1h)
        return {"label": label}

    def _compute_regime_snapshot(self, df_5h, df_12h, side):
        getter = getattr(self.regime_detector, "compute_regime_snapshot", None)
        if callable(getter):
            snapshot = getter(df_5h, df_12h, side=side)
            if isinstance(snapshot, dict):
                return snapshot
        raw_score = self.regime_detector.compute_regime(df_5h, df_12h, side=side)
        return {
            "side": side,
            "raw_score": raw_score,
            "class": self._regime_classification(raw_score),
            "allows_entries": self._regime_allows_entry(raw_score),
        }

    def _risk_for_side(self, side):
        return self.risk_per_trade_by_side.get(str(side).lower(), self.risk_per_trade)

    def _trade_role(self, trade):
        if trade is None:
            return None
        role = getattr(trade, "entry_role", None)
        if role:
            return str(role).lower()
        multiplier = float(getattr(trade, "entry_risk_multiplier", 1.0) or 1.0)
        return "support" if multiplier < 1.0 else "core"

    def _trade_priority(self, trade):
        if trade is None:
            return None
        priority = getattr(trade, "entry_priority", None)
        if priority is not None:
            return int(priority)
        return 0 if self._trade_role(trade) == "support" else 1

    def _entry_metadata(self, score, side):
        preview = getattr(self.entry_engine, "preview_entry_metadata", None)
        if callable(preview):
            return dict(preview(score, side))

        threshold_getter = getattr(self.entry_engine, "entry_threshold_for_side", None)
        if callable(threshold_getter):
            entry_threshold = int(threshold_getter(side))
        else:
            entry_threshold = self.config.require("entry", "score_threshold")

        return {
            "entry_threshold": entry_threshold,
            "entry_risk_multiplier": 1.0,
            "entry_role": "core",
            "entry_priority": 1,
        }

    def _select_weighted_candidate(
        self,
        row,
        bias,
        df_5h,
        df_12h,
        minimum_priority=None,
        bias_snapshot=None,
    ):
        directional_candidates = []

        long_regime_snapshot = (
            self._compute_regime_snapshot(df_5h, df_12h, side="long")
            if "long" in self.enabled_sides
            else None
        )
        short_regime_snapshot = (
            self._compute_regime_snapshot(df_5h, df_12h, side="short")
            if "short" in self.enabled_sides
            else None
        )
        long_regime = (
            long_regime_snapshot.get("raw_score")
            if long_regime_snapshot is not None
            else None
        )
        short_regime = (
            short_regime_snapshot.get("raw_score")
            if short_regime_snapshot is not None
            else None
        )
        long_regime_class = (
            long_regime_snapshot.get("class")
            if long_regime_snapshot is not None
            else None
        )
        short_regime_class = (
            short_regime_snapshot.get("class")
            if short_regime_snapshot is not None
            else None
        )

        candidate_builder = getattr(self.entry_engine, "build_candidate", None)
        if not callable(candidate_builder):
            weighted_evaluator = getattr(
                self.entry_engine,
                "evaluate_weighted_opportunity",
                None,
            )
            if not callable(weighted_evaluator):
                raise AttributeError(
                    "Weighted entry mode requires build_candidate() or "
                    "evaluate_weighted_opportunity()"
                )
            candidate_builder = weighted_evaluator

        print("\nDirectional regime context")
        print(f"  LONG:  {long_regime} ({long_regime_class})")
        print(f"  SHORT: {short_regime} ({short_regime_class})")

        if "long" in self.enabled_sides:
            score_details_getter = getattr(
                self.score_engine,
                "compute_score_details",
                None,
            )
            long_score_details = (
                score_details_getter(row, bias, side="long")
                if callable(score_details_getter)
                else None
            )
            long_score = (
                long_score_details["score"]
                if long_score_details is not None
                else self.score_engine.compute_score(row, bias, side="long")
            )
            long_profile = candidate_builder(
                row,
                long_score,
                bias,
                side="long",
                regime_score=long_regime,
                regime_class=long_regime_class,
                score_details=long_score_details,
            )
            self._enrich_opportunity_payload(
                long_profile,
                bias_snapshot=bias_snapshot or {"label": bias},
                regime_snapshot=long_regime_snapshot,
            )
            self._assign_opportunity_id(long_profile)
            self._log_opportunity(long_profile)
            long_candidate = long_profile.get("candidate")
            if long_candidate is not None:
                long_candidate["bias_snapshot"] = bias_snapshot or {"label": bias}
                long_candidate["regime_snapshot"] = long_regime_snapshot
                directional_candidates.append(long_candidate)
            print(
                "  LONG strength: "
                f"{long_profile['final_strength']:.4f} "
                f"(score={long_score}, eligible={long_profile['eligible']})"
            )

        if "short" in self.enabled_sides:
            score_details_getter = getattr(
                self.score_engine,
                "compute_score_details",
                None,
            )
            short_score_details = (
                score_details_getter(row, bias, side="short")
                if callable(score_details_getter)
                else None
            )
            short_score = (
                short_score_details["score"]
                if short_score_details is not None
                else self.score_engine.compute_score(row, bias, side="short")
            )
            short_profile = candidate_builder(
                row,
                short_score,
                bias,
                side="short",
                regime_score=short_regime,
                regime_class=short_regime_class,
                score_details=short_score_details,
            )
            self._enrich_opportunity_payload(
                short_profile,
                bias_snapshot=bias_snapshot or {"label": bias},
                regime_snapshot=short_regime_snapshot,
            )
            self._assign_opportunity_id(short_profile)
            self._log_opportunity(short_profile)
            short_candidate = short_profile.get("candidate")
            if short_candidate is not None:
                short_candidate["bias_snapshot"] = bias_snapshot or {"label": bias}
                short_candidate["regime_snapshot"] = short_regime_snapshot
                directional_candidates.append(short_candidate)
            print(
                "  SHORT strength: "
                f"{short_profile['final_strength']:.4f} "
                f"(score={short_score}, eligible={short_profile['eligible']})"
            )

        if long_regime is not None:
            exploratory_long = self.exploration_engine.build_candidate(
                row,
                bias=bias,
                side="long",
                regime_score=long_regime,
                regime_class=long_regime_class,
            )
            if exploratory_long is not None:
                directional_candidates.append(exploratory_long)

        if short_regime is not None:
            exploratory_short = self.exploration_engine.build_candidate(
                row,
                bias=bias,
                side="short",
                regime_score=short_regime,
                regime_class=short_regime_class,
            )
            if exploratory_short is not None:
                directional_candidates.append(exploratory_short)

        candidate = self._choose_direction(directional_candidates)
        if candidate is None:
            print("No entry: no weighted directional edge beat the noise guard cleanly")
            return None

        if (
            minimum_priority is not None
            and candidate["entry_priority"] <= int(minimum_priority)
        ):
            print("No entry: no higher-priority directional edge is available")
            return None

        print(f"Selected direction: {candidate['side'].upper()}")
        print(f"Selected role: {candidate['entry_role'].upper()}")
        print(
            "Selected strength: "
            f"{float(candidate.get('selection_value', candidate.get('score', 0))):.4f}"
        )
        print(f"Selected signal family: {candidate.get('signal_family', 'trend').upper()}")
        return candidate

    def _select_directional_candidate(
        self,
        row,
        bias,
        df_5h,
        df_12h,
        minimum_priority=None,
        bias_snapshot=None,
    ):
        if self.weighted_entry_mode:
            return self._select_weighted_candidate(
                row,
                bias,
                df_5h,
                df_12h,
                minimum_priority=minimum_priority,
                bias_snapshot=bias_snapshot,
            )

        long_regime_snapshot = (
            self._compute_regime_snapshot(df_5h, df_12h, side="long")
            if "long" in self.enabled_sides
            else None
        )
        short_regime_snapshot = (
            self._compute_regime_snapshot(df_5h, df_12h, side="short")
            if "short" in self.enabled_sides
            else None
        )
        long_regime = (
            long_regime_snapshot.get("raw_score")
            if long_regime_snapshot is not None
            else None
        )
        short_regime = (
            short_regime_snapshot.get("raw_score")
            if short_regime_snapshot is not None
            else None
        )
        long_allowed = (
            self._regime_allows_entry(long_regime_snapshot)
            if long_regime_snapshot is not None
            else False
        )
        short_allowed = (
            self._regime_allows_entry(short_regime_snapshot)
            if short_regime_snapshot is not None
            else False
        )

        if not long_allowed and not short_allowed:
            print(
                "No entry: both directional regimes are too weak "
                f"(LONG={long_regime}, SHORT={short_regime})"
            )
            return None

        score_details_getter = getattr(
            self.score_engine,
            "compute_score_details",
            None,
        )
        long_score_details = (
            score_details_getter(row, bias, side="long")
            if "long" in self.enabled_sides and long_allowed and callable(score_details_getter)
            else None
        )
        short_score_details = (
            score_details_getter(row, bias, side="short")
            if "short" in self.enabled_sides and short_allowed and callable(score_details_getter)
            else None
        )
        long_score = (
            long_score_details["score"]
            if long_score_details is not None
            else (
                self.score_engine.compute_score(row, bias, side="long")
                if "long" in self.enabled_sides and long_allowed
                else -1
            )
        )
        short_score = (
            short_score_details["score"]
            if short_score_details is not None
            else (
                self.score_engine.compute_score(row, bias, side="short")
                if "short" in self.enabled_sides and short_allowed
                else -1
            )
        )
        long_meta = self._entry_metadata(long_score, "long")
        short_meta = self._entry_metadata(short_score, "short")

        print("\nDirectional regime gate")
        print(f"  LONG:  {long_regime} ({'ALLOW' if long_allowed else 'BLOCK'})")
        print(f"  SHORT: {short_regime} ({'ALLOW' if short_allowed else 'BLOCK'})")
        print("\nDirectional scorecard")
        print(f"  LONG:  {long_score} (threshold {long_meta['entry_threshold']})")
        print(f"  SHORT: {short_score} (threshold {short_meta['entry_threshold']})")

        directional_candidates = []

        long_candidate = None
        if long_allowed and long_score >= long_meta["entry_threshold"]:
            long_candidate = {
                "side": "long",
                "score": long_score,
                "trade_regime": long_regime,
                "regime_class": (
                    long_regime_snapshot.get("class")
                    if long_regime_snapshot is not None
                    else None
                ),
                "score_details": long_score_details,
                "bias_snapshot": bias_snapshot or {"label": bias},
                "regime_snapshot": long_regime_snapshot,
                "signal_family": "trend",
                **long_meta,
            }
            directional_candidates.append(long_candidate)

        short_candidate = None
        if short_allowed and short_score >= short_meta["entry_threshold"]:
            short_candidate = {
                "side": "short",
                "score": short_score,
                "trade_regime": short_regime,
                "regime_class": (
                    short_regime_snapshot.get("class")
                    if short_regime_snapshot is not None
                    else None
                ),
                "score_details": short_score_details,
                "bias_snapshot": bias_snapshot or {"label": bias},
                "regime_snapshot": short_regime_snapshot,
                "signal_family": "trend",
                **short_meta,
            }
            directional_candidates.append(short_candidate)

        if long_allowed:
            exploratory_long = self.exploration_engine.build_candidate(
                row,
                bias=bias,
                side="long",
                regime_score=long_regime,
                regime_class=(
                    long_regime_snapshot.get("class")
                    if long_regime_snapshot is not None
                    else None
                ),
            )
            if exploratory_long is not None:
                directional_candidates.append(exploratory_long)

        if short_allowed:
            exploratory_short = self.exploration_engine.build_candidate(
                row,
                bias=bias,
                side="short",
                regime_score=short_regime,
                regime_class=(
                    short_regime_snapshot.get("class")
                    if short_regime_snapshot is not None
                    else None
                ),
            )
            if exploratory_short is not None:
                directional_candidates.append(exploratory_short)

        candidate = self._choose_direction(directional_candidates)
        if candidate is None:
            print("No entry: no directional edge beat threshold cleanly")
            return None

        if (
            minimum_priority is not None
            and candidate["entry_priority"] <= int(minimum_priority)
        ):
            print("No entry: no higher-priority directional edge is available")
            return None

        print(f"Selected direction: {candidate['side'].upper()}")
        print(f"Selected role: {candidate['entry_role'].upper()}")
        print(f"Selected signal family: {candidate.get('signal_family', 'trend').upper()}")

        trade = candidate.get("trade")
        if trade is None:
            candidate_builder = getattr(self.entry_engine, "build_candidate", None)
            if callable(candidate_builder):
                profile = candidate_builder(
                    row,
                    candidate["score"],
                    bias,
                    side=candidate["side"],
                    regime_score=candidate["trade_regime"],
                    regime_class=candidate["regime_class"],
                    score_details=candidate.get("score_details"),
                )
                built_candidate = profile.get("candidate")
                if built_candidate is None:
                    return None
                candidate.update(built_candidate)
                trade = built_candidate.get("trade")
            else:
                trade = self.entry_engine.generate_entry(
                    row,
                    candidate["score"],
                    bias,
                    side=candidate["side"],
                    regime_score=candidate["trade_regime"],
                    regime_class=candidate["regime_class"],
                )
                if trade is None:
                    return None
                candidate["trade"] = trade

        trade = candidate.get("trade")
        candidate["entry_risk_multiplier"] = float(
            getattr(trade, "entry_risk_multiplier", candidate["entry_risk_multiplier"])
            or candidate["entry_risk_multiplier"]
        )
        candidate["entry_role"] = str(
            getattr(trade, "entry_role", candidate["entry_role"])
        ).lower()
        candidate["entry_priority"] = int(
            getattr(trade, "entry_priority", candidate["entry_priority"])
        )
        candidate["signal_family"] = str(
            getattr(trade, "signal_family", candidate.get("signal_family", "trend"))
        ).lower()
        return candidate

    def _open_candidate_trade(self, row, bias, candidate):
        trade = candidate["trade"]
        opportunity_id = candidate.get("opportunity_id")
        if opportunity_id is not None:
            if hasattr(trade, "annotate_opportunity") and callable(trade.annotate_opportunity):
                trade.annotate_opportunity(opportunity_id)
            else:
                trade.opportunity_id = opportunity_id
        selected_side = candidate["side"]
        trade_regime = candidate["trade_regime"]
        regime_class = candidate["regime_class"]
        entry_threshold = candidate["entry_threshold"]
        bias_snapshot = candidate.get("bias_snapshot")
        regime_snapshot = candidate.get("regime_snapshot")

        if hasattr(trade, "annotate_entry_context") and callable(trade.annotate_entry_context):
            trade.annotate_entry_context(
                bias=bias,
                regime_score=trade_regime,
                regime_class=regime_class,
                entry_threshold=entry_threshold,
                bias_snapshot=bias_snapshot,
                regime_snapshot=regime_snapshot,
            )
        else:
            trade.bias = bias
            trade.regime_score = trade_regime
            trade.regime_class = regime_class
            trade.entry_threshold = entry_threshold

        trade.entry_role = str(
            getattr(trade, "entry_role", candidate.get("entry_role", "core"))
        ).lower()
        trade.entry_priority = int(
            getattr(trade, "entry_priority", candidate.get("entry_priority", 1))
        )
        if hasattr(trade, "annotate_signal_family") and callable(trade.annotate_signal_family):
            trade.annotate_signal_family(
                candidate.get("signal_family", getattr(trade, "signal_family", "trend")),
                pressure_score=getattr(trade, "pressure_score", None),
            )

        print("\nEXECUTING NEW TRADE")
        base_side_risk_per_trade = self._risk_for_side(selected_side)
        entry_risk_multiplier = float(
            getattr(trade, "entry_risk_multiplier", 1.0) or 1.0
        )
        applied_risk_per_trade = (
            base_side_risk_per_trade * entry_risk_multiplier
        )

        size = self.position_sizer.calculate(
            equity=self.account.equity,
            risk_per_trade=applied_risk_per_trade,
            entry_price=row["close"],
            stop_price=trade.stop
        )

        if size <= 0:
            print("Entry skipped: position size invalid")
            return False

        initial_risk_amount = abs(row["close"] - trade.stop) * size
        effective_risk_fraction = (
            initial_risk_amount / self.account.equity
            if self.account.equity
            else 0.0
        )
        if hasattr(trade, "annotate_risk_context") and callable(trade.annotate_risk_context):
            trade.annotate_risk_context(
                equity_at_entry=self.account.equity,
                entry_risk_multiplier=entry_risk_multiplier,
                intended_risk_per_trade=applied_risk_per_trade,
                effective_risk_fraction=effective_risk_fraction,
            )
        trade.add_entry(row["close"], size)

        self.current_trade = trade
        self.base_size = size
        self.level = 0
        return True

    # --------------------------------------------------
    # Main step function (called each 15m candle)
    # --------------------------------------------------

    def step(self, row, df_1h, df_5h, df_12h):
        """
        Process one execution-timeframe candle.

        The method receives the current execution row plus higher-timeframe
        slices that should already be restricted to data available at that
        timestamp. It then performs context detection, entry checks, open-trade
        management, exit handling, and optional logging.
        """

        print("\n" + "=" * 60)
        print(f"Processing candle: {row.name}")

        # --------------------------
        # 1. MARKET CONTEXT
        # --------------------------

        bias_snapshot = self._compute_bias_snapshot(df_1h)
        bias = str(bias_snapshot.get("label", "neutral"))

        # --------------------------
        # 2. ENTRY LOGIC
        # --------------------------

        if self.current_trade is None:
            candidate = self._select_directional_candidate(
                row,
                bias,
                df_5h,
                df_12h,
                bias_snapshot=bias_snapshot,
            )
            if candidate:
                self._open_candidate_trade(row, bias, candidate)

        # --------------------------
        # 3. TRADE MANAGEMENT
        # --------------------------

        else:

            print("\nManaging open trade...")

            trade = self.current_trade
            side = getattr(trade, "side", "long")
            current_role = self._trade_role(trade)
            current_priority = self._trade_priority(trade)
            active_stop = float(getattr(trade, "active_stop", trade.stop))

            override_candidate = None
            if current_role == "support":
                candidate = self._select_directional_candidate(
                    row,
                    bias,
                    df_5h,
                    df_12h,
                    minimum_priority=current_priority,
                    bias_snapshot=bias_snapshot,
                )
                if candidate is not None:
                    override_candidate = candidate
                    print(
                        "\nHigher-priority candidate detected -> "
                        f"{candidate['entry_role'].upper()} trade can override SUPPORT position"
                    )

            hard_exit_signal = self.exit_engine.should_exit(
                row,
                active_stop,
                side=side,
            )

            if hard_exit_signal:
                exit_reason = "trailing stop" if active_stop != trade.stop else "hard exit"
                self._close_current_trade(
                    row,
                    reason=exit_reason,
                    exit_price=active_stop,
                )
                if override_candidate is not None:
                    self._open_candidate_trade(row, bias, override_candidate)

            elif override_candidate is not None:
                self._close_current_trade(row, reason="core override")
                self._open_candidate_trade(row, bias, override_candidate)

            else:
                evaluate = getattr(self.trend_sniffer, "evaluate", None)
                if callable(evaluate):
                    trailing_signal = evaluate(row, trade=trade)
                    trend_ok = bool(trailing_signal["trend_alive"])
                    soft_exit_signal = bool(trailing_signal["should_exit"])
                    if hasattr(trade, "update_trailing_state") and callable(trade.update_trailing_state):
                        trade.update_trailing_state(
                            trail_state=trailing_signal["state"],
                            anchor_column=trailing_signal["anchor_column"],
                            anchor_price=trailing_signal["anchor_price"],
                            open_r_multiple=trailing_signal["open_r_multiple"],
                            momentum_score=trailing_signal["momentum_score"],
                            decay_score=trailing_signal["decay_score"],
                            proposed_stop=(
                                None if soft_exit_signal else trailing_signal["proposed_stop"]
                            ),
                        )
                    allow_pyramiding = bool(
                        trailing_signal.get("allow_pyramiding", trend_ok)
                    )
                else:
                    trend_ok = self.trend_sniffer.is_trend_alive(row, trade=trade)
                    soft_exit_signal = not trend_ok
                    allow_pyramiding = trend_ok

                if soft_exit_signal:
                    exit_reason = "state exit" if getattr(trade, "trail_state", None) == "exit" else "trend weakness"
                    self._close_current_trade(row, reason=exit_reason)
                    if override_candidate is not None:
                        self._open_candidate_trade(row, bias, override_candidate)
                    if self.equity_logger:
                        self.equity_logger.log(row.name, self.account.equity)
                    print("=" * 60 + "\n")
                    return

                price = row["close"]
                # Pyramiding is allowed only while the trade remains valid.
                pyramid_quality_ok = self.pyramiding_engine.qualifies_for_pyramiding(
                    row=row,
                    trade=trade,
                )
                new_level = self.pyramiding_engine.check_pyramiding(
                    price=price,
                    entry_price=trade.entry_price,
                    R=trade.R,
                    current_level=self.level,
                    trend_ok=trend_ok and allow_pyramiding and pyramid_quality_ok,
                    previous_price=row.get("prev_close"),
                    side=side,
                )

                if new_level != self.level:
                    add_size = self.pyramiding_engine.get_pyramid_size(
                        self.base_size,
                        new_level,
                        quality_gate_passed=pyramid_quality_ok,
                    )

                    if add_size > 0:
                        current_risk = trade.total_risk_to_stop()
                        trade_risk_per_trade = getattr(
                            trade,
                            "intended_risk_per_trade",
                            None,
                        )
                        if trade_risk_per_trade is None:
                            trade_risk_per_trade = self._risk_for_side(side)
                        add_size = self.pyramiding_engine.cap_add_size_by_risk(
                            add_size=add_size,
                            add_price=price,
                            stop_price=trade.stop,
                            current_total_risk=current_risk,
                            equity=self.account.equity,
                            risk_per_trade=trade_risk_per_trade,
                            quality_gate_passed=pyramid_quality_ok,
                        )

                        if add_size > 0:
                            trade.add_entry(price, add_size)
                            self.level = new_level
                            trade.pyramid_level = new_level

        if self.equity_logger:
            self.equity_logger.log(row.name, self.account.equity)

        print("=" * 60 + "\n")

    # --------------------------------------------------
    # Summary (end of run)
    # --------------------------------------------------

    def summary(self):
        self.account.summary()

    def snapshot_state(self):
        return {
            "account": self.account.snapshot(),
            "current_trade": (
                self.current_trade.snapshot()
                if self.current_trade is not None
                else None
            ),
            "base_size": self.base_size,
            "level": self.level,
        }

    def restore_state(self, snapshot):
        if not snapshot:
            return

        account_snapshot = snapshot.get("account")
        if account_snapshot:
            self.account.restore(account_snapshot)

        trade_snapshot = snapshot.get("current_trade")
        if trade_snapshot:
            self.current_trade = Trade.from_snapshot(
                trade_snapshot,
                config=self.config,
            )
        else:
            self.current_trade = None

        self.base_size = snapshot.get("base_size", 0)
        self.level = snapshot.get("level", 0)
