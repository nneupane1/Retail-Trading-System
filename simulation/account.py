"""Tracks simulated equity and trade statistics across the strategy run."""

import time
from config import AppConfig


class Account:
    """
    Simulated trading account.

    Tracks:
    - Total equity
    - Trade updates (PnL)
    """

    def __init__(self, initial_equity=None, config=None):

        print("\nInitializing account...")

        start = time.time()

        self.config = config or AppConfig.load()
        initial_equity = initial_equity or self.config.require("account", "initial_equity")

        self.initial_equity = initial_equity
        self.equity = initial_equity

        self.trade_count = 0
        self.win_count = 0
        self.loss_count = 0

        print(f"Account initialized")
        print(f"  Starting equity: {self.equity:.2f}")

        print(f"Init elapsed: {time.time() - start:.4f}s")

    # ------------------------------------------
    # Update account after trade closes
    # ------------------------------------------

    def update(self, trade):
        """
        Apply trade results to account.
        """

        print("\nUpdating account with trade result...")

        start = time.time()

        pnl = trade.pnl

        # update equity
        self.equity += pnl

        # update stats
        self.trade_count += 1

        if pnl > 0:
            self.win_count += 1
            outcome = "WIN"
        else:
            self.loss_count += 1
            outcome = "LOSS"

        # stats
        win_rate = (self.win_count / self.trade_count) * 100

        print(f"\n{outcome}")
        print(f"  Trade PnL: {pnl:.2f}")
        print(f"  New equity: {self.equity:.2f}")

        print(f"\nStats:")
        print(f"  Trades: {self.trade_count}")
        print(f"  Wins:   {self.win_count}")
        print(f"  Losses: {self.loss_count}")
        print(f"  Win rate: {win_rate:.2f}%")

        print(f"\nNet PnL: {self.equity - self.initial_equity:.2f}")

        print(f"Elapsed: {time.time() - start:.4f}s")

    # ------------------------------------------
    # Optional: current snapshot
    # ------------------------------------------

    def summary(self):
        """
        Print current account summary.
        """

        print("\nACCOUNT SUMMARY")
        print(f"  Initial equity: {self.initial_equity:.2f}")
        print(f"  Current equity: {self.equity:.2f}")
        print(f"  Net PnL: {self.equity - self.initial_equity:.2f}")
        print(f"  Trades: {self.trade_count}")

        if self.trade_count > 0:
            win_rate = (self.win_count / self.trade_count) * 100
            print(f"  Win rate: {win_rate:.2f}%")
