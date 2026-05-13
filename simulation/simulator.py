import time

from simulation.account import Account
from simulation.trade import Trade

from core.bias.bias_detector import get_bias
from core.regime.regime_detector import compute_regime
from core.entry.scoring import compute_score
from core.entry.entry_engine import generate_entry

from core.position.sizing import calculate_position_size
from core.pyramiding.pyramiding_engine import check_pyramiding, get_pyramid_size
from core.sniffing.trend_sniffer import is_trend_alive
from core.exit.exit_engine import should_exit


class Simulator:
    """
    Core engine running your strategy step-by-step (candle-based).
    """

    def __init__(self, initial_equity=20000):

        print("\n🧠 Initializing Simulator...")

        self.account = Account(initial_equity=initial_equity)

        self.current_trade = None
        self.base_size = 0
        self.level = 0

    # ✅ --------------------------------------------------
    # Main step function (called each 15m candle)
    # ✅ --------------------------------------------------

    def step(self, row, df_1h, df_5h, df_12h):

        print("\n" + "=" * 60)
        print(f"⏱ Processing candle: {row.name}")

        # ✅ --------------------------
        # 1. MARKET CONTEXT
        # ✅ --------------------------

        bias = get_bias(df_1h)
        regime = compute_regime(df_5h, df_12h)

        # ✅ --------------------------
        # 2. ENTRY LOGIC
        # ✅ --------------------------

        score = compute_score(row, bias)

        if self.current_trade is None:

            trade = generate_entry(row, score, bias)

            if trade:

                print("\n🚀 EXECUTING NEW TRADE")

                # ✅ position sizing
                size = calculate_position_size(
                    equity=self.account.equity,
                    risk_per_trade=0.01,
                    entry_price=row["close"],
                    stop_price=row["ll10"]
                )

                trade.add_entry(row["close"], size)

                self.current_trade = trade
                self.base_size = size
                self.level = 0

        # ✅ --------------------------
        # 3. TRADE MANAGEMENT
        # ✅ --------------------------

        else:

            print("\n📈 Managing open trade...")

            price = row["close"]
            trade = self.current_trade

            # ✅ pyramiding
            new_level = check_pyramiding(
                price=price,
                entry_price=trade.entry_price,
                R=trade.R,
                current_level=self.level
            )

            if new_level != self.level:
                add_size = get_pyramid_size(self.base_size, new_level)

                if add_size > 0:
                    trade.add_entry(price, add_size)
                    self.level = new_level

            # ✅ sniffing (trend continuation)
            trend_ok = is_trend_alive(row)

            # ✅ exit logic
            exit_signal = should_exit(row, trade.stop)

            # ✅ combine exit logic
            if exit_signal or not trend_ok:

                print("\n🏁 EXITING TRADE")

                trade.close(row)

                # ✅ update account
                self.account.update(trade)

                # ✅ reset
                self.current_trade = None
                self.base_size = 0
                self.level = 0

        print("=" * 60 + "\n")

    # ✅ --------------------------------------------------
    # Summary (end of run)
    # ✅ --------------------------------------------------

    def summary(self):
        self.account.summary()
