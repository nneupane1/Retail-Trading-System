"""Coordinates strategy context, entries, management, exits, account updates, and logging."""

import time

from config import AppConfig
from simulation.account import Account

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

        # --------------------------
        # 2. ENTRY LOGIC
        # --------------------------

        score = self.score_engine.compute_score(row, bias)

        if self.current_trade is None:

            trade = self.entry_engine.generate_entry(row, score, bias)

            if trade:

                print("\nEXECUTING NEW TRADE")

                # position sizing
                size = self.position_sizer.calculate(
                    equity=self.account.equity,
                    risk_per_trade=self.risk_per_trade,
                    entry_price=row["close"],
                    stop_price=trade.stop
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

            # pyramiding
            new_level = self.pyramiding_engine.check_pyramiding(
                price=price,
                entry_price=trade.entry_price,
                R=trade.R,
                current_level=self.level
            )

            if new_level != self.level:
                add_size = self.pyramiding_engine.get_pyramid_size(
                    self.base_size,
                    new_level
                )

                if add_size > 0:
                    trade.add_entry(price, add_size)
                    self.level = new_level

            # sniffing (trend continuation)
            trend_ok = self.trend_sniffer.is_trend_alive(row)

            # exit logic
            exit_signal = self.exit_engine.should_exit(row, trade.stop)

            # combine exit logic
            if exit_signal or not trend_ok:

                print("\nEXITING TRADE")

                trade.close(row)

                # update account
                self.account.update(trade)

                if self.trade_logger:
                    self.trade_logger.log_trade(trade)

                # reset
                self.current_trade = None
                self.base_size = 0
                self.level = 0

        if self.equity_logger:
            self.equity_logger.log(row.name, self.account.equity)

        print("=" * 60 + "\n")

    # --------------------------------------------------
    # Summary (end of run)
    # --------------------------------------------------

    def summary(self):
        self.account.summary()
