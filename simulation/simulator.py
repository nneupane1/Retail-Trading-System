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

    @staticmethod
    def _choose_direction(long_score, short_score, threshold):
        long_valid = long_score >= threshold
        short_valid = short_score >= threshold

        if long_valid and long_score > short_score:
            return "long"
        if short_valid and short_score > long_score:
            return "short"
        return None

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
        if regime_score is None:
            return False
        allows_entries = getattr(self.regime_detector, "allows_entries", None)
        if callable(allows_entries):
            return allows_entries(regime_score)
        return True

    def _regime_classification(self, regime_score):
        classify = getattr(self.regime_detector, "classify", None)
        if callable(classify):
            return classify(regime_score)
        return None

    def _risk_for_side(self, side):
        return self.risk_per_trade_by_side.get(str(side).lower(), self.risk_per_trade)

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

        bias = self.bias_detector.get_bias(df_1h)
        entry_threshold = self.config.require("entry", "score_threshold")

        # --------------------------
        # 2. ENTRY LOGIC
        # --------------------------

        if self.current_trade is None:
            long_regime = (
                self.regime_detector.compute_regime(df_5h, df_12h, side="long")
                if "long" in self.enabled_sides
                else None
            )
            short_regime = (
                self.regime_detector.compute_regime(df_5h, df_12h, side="short")
                if "short" in self.enabled_sides
                else None
            )
            long_allowed = (
                self._regime_allows_entry(long_regime)
                if long_regime is not None
                else False
            )
            short_allowed = (
                self._regime_allows_entry(short_regime)
                if short_regime is not None
                else False
            )

            if not long_allowed and not short_allowed:
                print(
                    "No entry: both directional regimes are too weak "
                    f"(LONG={long_regime}, SHORT={short_regime})"
                )
            else:
                long_score = (
                    self.score_engine.compute_score(row, bias, side="long")
                    if "long" in self.enabled_sides and long_allowed
                    else -1
                )
                short_score = (
                    self.score_engine.compute_score(row, bias, side="short")
                    if "short" in self.enabled_sides and short_allowed
                    else -1
                )
                print("\nDirectional regime gate")
                print(f"  LONG:  {long_regime} ({'ALLOW' if long_allowed else 'BLOCK'})")
                print(f"  SHORT: {short_regime} ({'ALLOW' if short_allowed else 'BLOCK'})")
                print("\nDirectional scorecard")
                print(f"  LONG:  {long_score}")
                print(f"  SHORT: {short_score}")

                selected_side = self._choose_direction(
                    long_score=long_score,
                    short_score=short_score,
                    threshold=entry_threshold,
                )
                if selected_side is None:
                    print("No entry: no directional edge beat threshold cleanly")
                    trade = None
                    score = None
                else:
                    score = long_score if selected_side == "long" else short_score
                    print(f"Selected direction: {selected_side.upper()}")
                    trade = self.entry_engine.generate_entry(
                        row,
                        score,
                        bias,
                        side=selected_side,
                    )

                if trade:
                    trade_regime = long_regime if selected_side == "long" else short_regime
                    regime_class = self._regime_classification(trade_regime)
                    if hasattr(trade, "annotate_entry_context") and callable(trade.annotate_entry_context):
                        trade.annotate_entry_context(
                            bias=bias,
                            regime_score=trade_regime,
                            regime_class=regime_class,
                            entry_threshold=entry_threshold,
                        )
                    else:
                        trade.bias = bias
                        trade.regime_score = trade_regime
                        trade.regime_class = regime_class
                        trade.entry_threshold = entry_threshold

                    print("\nEXECUTING NEW TRADE")
                    side_risk_per_trade = self._risk_for_side(selected_side)

                    size = self.position_sizer.calculate(
                        equity=self.account.equity,
                        risk_per_trade=side_risk_per_trade,
                        entry_price=row["close"],
                        stop_price=trade.stop
                    )

                    if size <= 0:
                        print("Entry skipped: position size invalid")
                    else:
                        initial_risk_amount = abs(row["close"] - trade.stop) * size
                        effective_risk_fraction = (
                            initial_risk_amount / self.account.equity
                            if self.account.equity
                            else 0.0
                        )
                        if hasattr(trade, "annotate_risk_context") and callable(trade.annotate_risk_context):
                            trade.annotate_risk_context(
                                equity_at_entry=self.account.equity,
                                intended_risk_per_trade=side_risk_per_trade,
                                effective_risk_fraction=effective_risk_fraction,
                            )
                        trade.add_entry(row["close"], size)

                        self.current_trade = trade
                        self.base_size = size
                        self.level = 0

        # --------------------------
        # 3. TRADE MANAGEMENT
        # --------------------------

        else:

            print("\nManaging open trade...")

            price = row["close"]
            trade = self.current_trade
            side = getattr(trade, "side", "long")

            trend_ok = self.trend_sniffer.is_trend_alive(row, trade=trade)
            hard_exit_signal = self.exit_engine.should_exit(row, trade.stop, side=side)
            soft_exit_signal = not trend_ok

            if hard_exit_signal:
                self._close_current_trade(
                    row,
                    reason="hard exit",
                    exit_price=trade.stop,
                )

            elif soft_exit_signal:
                self._close_current_trade(row, reason="trend weakness")

            else:
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
                    trend_ok=trend_ok and pyramid_quality_ok,
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
                        side_risk_per_trade = self._risk_for_side(side)
                        add_size = self.pyramiding_engine.cap_add_size_by_risk(
                            add_size=add_size,
                            add_price=price,
                            stop_price=trade.stop,
                            current_total_risk=current_risk,
                            equity=self.account.equity,
                            risk_per_trade=side_risk_per_trade,
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
