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
        self.risk_per_trade = (
            risk_per_trade
            if risk_per_trade is not None
            else self.config.require("account", "risk_per_trade")
        )

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
        allows_entries = getattr(self.regime_detector, "allows_entries", None)
        if callable(allows_entries):
            return allows_entries(regime_score)
        return True

    def _regime_classification(self, regime_score):
        classify = getattr(self.regime_detector, "classify", None)
        if callable(classify):
            return classify(regime_score)
        return None

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
        regime = self.regime_detector.compute_regime(df_5h, df_12h)
        regime_class = self._regime_classification(regime)
        entry_threshold = self.config.require("entry", "score_threshold")

        # --------------------------
        # 2. ENTRY LOGIC
        # --------------------------

        if self.current_trade is None:
            if not self._regime_allows_entry(regime):
                print(f"No entry: regime too weak ({regime})")
            else:
                score = self.score_engine.compute_score(row, bias)

                trade = self.entry_engine.generate_entry(row, score, bias)

                if trade:
                    if hasattr(trade, "annotate_entry_context") and callable(trade.annotate_entry_context):
                        trade.annotate_entry_context(
                            bias=bias,
                            regime_score=regime,
                            regime_class=regime_class,
                            entry_threshold=entry_threshold,
                        )
                    else:
                        trade.bias = bias
                        trade.regime_score = regime
                        trade.regime_class = regime_class
                        trade.entry_threshold = entry_threshold

                    print("\nEXECUTING NEW TRADE")

                    # position sizing
                    size = self.position_sizer.calculate(
                        equity=self.account.equity,
                        risk_per_trade=self.risk_per_trade,
                        entry_price=row["close"],
                        stop_price=trade.stop
                    )

                    if size <= 0:
                        print("Entry skipped: position size invalid")
                    else:
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

            # TrendSniffer is the primary soft-exit signal.
            # ExitEngine remains reserved for hard exits such as the stop.
            trend_ok = self.trend_sniffer.is_trend_alive(row)
            hard_exit_signal = self.exit_engine.should_exit(row, trade.stop)
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
                new_level = self.pyramiding_engine.check_pyramiding(
                    price=price,
                    entry_price=trade.entry_price,
                    R=trade.R,
                    current_level=self.level,
                    trend_ok=trend_ok,
                    previous_price=row.get("prev_close")
                )

                if new_level != self.level:
                    add_size = self.pyramiding_engine.get_pyramid_size(
                        self.base_size,
                        new_level
                    )

                    if add_size > 0:
                        current_risk = trade.total_risk_to_stop()
                        add_size = self.pyramiding_engine.cap_add_size_by_risk(
                            add_size=add_size,
                            add_price=price,
                            stop_price=trade.stop,
                            current_total_risk=current_risk,
                            equity=self.account.equity,
                            risk_per_trade=self.risk_per_trade
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
