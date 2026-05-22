"""Rich-based live console display for the historical backtest pipeline."""

from collections import deque
from datetime import datetime

try:
    from rich import box
    from rich.console import Console, Group
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )
    from rich.table import Table

    RICH_AVAILABLE = True
except ImportError:  # pragma: no cover - fallback path only
    RICH_AVAILABLE = False


def _fmt_duration(seconds):
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


class BacktestProgressDisplay:
    """
    Live terminal UI for the historical backtest pipeline.
    """

    def __init__(self, enabled=True):
        self.enabled = enabled and RICH_AVAILABLE
        self.console = Console() if self.enabled else None
        self.live = None
        self.progress = None
        self.task_id = None
        self.events = deque(maxlen=10)
        self.state = {}

    def start(self, symbol, start_date, end_date, initial_equity):
        if not self.enabled:
            return

        self.state = {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "phase": "Preparing pipeline",
            "current_step": "-",
            "current_time": "-",
            "processed": 0,
            "total": 0,
            "progress_pct": 0.0,
            "elapsed": "0s",
            "eta": "-",
            "equity": initial_equity,
            "net_pnl": 0.0,
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": "0.00%",
            "open_trade": "No",
        }

        self.progress = Progress(
            SpinnerColumn(style="cyan"),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=None, complete_style="green", finished_style="green"),
            TaskProgressColumn(),
            TextColumn("|"),
            TimeElapsedColumn(),
            TextColumn("| ETA"),
            TimeRemainingColumn(),
            expand=True,
            console=self.console,
            transient=False,
            redirect_stdout=False,
            redirect_stderr=False,
        )
        self.task_id = self.progress.add_task(
            f"Backtesting {symbol}",
            total=100,
            completed=0,
        )

        self.live = Live(
            self._build_renderable(),
            console=self.console,
            refresh_per_second=6,
            transient=False,
        )
        self.live.start()
        self.add_event("start", "Backtest pipeline started")
        self.refresh()

    def stop(self):
        if not self.enabled:
            return

        if self.live is not None:
            self.live.stop()
            self.live = None

    def add_event(self, level, message):
        if not self.enabled:
            return

        timestamp = datetime.now().strftime("%H:%M:%S")
        self.events.appendleft((timestamp, level.upper(), message))
        self.refresh()

    def update_phase(self, phase, detail=None):
        if not self.enabled:
            return

        self.state["phase"] = phase
        if detail:
            self.add_event("phase", detail)
        else:
            self.refresh()

    def set_total_steps(self, total_steps):
        if not self.enabled:
            return

        self.state["total"] = max(0, int(total_steps))
        self.refresh()

    def update_backtest_step(
        self,
        processed_steps,
        total_steps,
        candle_time,
        elapsed_seconds,
        eta_seconds,
        equity,
        initial_equity,
        trades,
        wins,
        losses,
        open_trade,
    ):
        if not self.enabled:
            return

        progress_pct = 100.0 if total_steps <= 0 else (processed_steps / total_steps) * 100
        win_rate = "0.00%" if trades == 0 else f"{(wins / trades) * 100:.2f}%"

        self.state["phase"] = "Running strategy loop"
        self.state["current_step"] = f"{processed_steps:,}/{total_steps:,}"
        self.state["current_time"] = str(candle_time)
        self.state["processed"] = processed_steps
        self.state["total"] = total_steps
        self.state["progress_pct"] = progress_pct
        self.state["elapsed"] = _fmt_duration(elapsed_seconds)
        self.state["eta"] = _fmt_duration(eta_seconds)
        self.state["equity"] = equity
        self.state["net_pnl"] = equity - initial_equity
        self.state["trades"] = trades
        self.state["wins"] = wins
        self.state["losses"] = losses
        self.state["win_rate"] = win_rate
        self.state["open_trade"] = "Yes" if open_trade else "No"

        self.progress.update(self.task_id, completed=progress_pct)
        self.refresh()

    def complete(self, total_time_seconds):
        if not self.enabled:
            return

        self.state["phase"] = "Completed"
        self.state["elapsed"] = _fmt_duration(total_time_seconds)
        self.state["eta"] = "0s"
        self.state["progress_pct"] = 100.0
        self.progress.update(self.task_id, completed=100)
        self.add_event("done", "Backtest pipeline completed")

    def _build_header(self):
        title = (
            f"[bold]Historical Backtest[/bold]  "
            f"[cyan]{self.state['symbol']}[/cyan]"
        )
        subtitle = f"{self.state['start_date']} -> {self.state['end_date']}"
        return Panel(title, title="Retail Trading System", subtitle=subtitle, expand=True)

    def _build_status_table(self):
        table = Table(
            title="Backtest Status",
            box=box.SIMPLE_HEAVY,
            expand=True,
            show_header=False,
        )
        table.add_column("Field", style="bold cyan", no_wrap=True)
        table.add_column("Value", style="white")

        table.add_row("Phase", str(self.state["phase"]))
        table.add_row("Current step", str(self.state["current_step"]))
        table.add_row("Current candle", str(self.state["current_time"]))
        table.add_row("Progress", f"{self.state['progress_pct']:.2f}%")
        table.add_row("Elapsed", self.state["elapsed"])
        table.add_row("ETA", self.state["eta"])
        table.add_row("Equity", f"{self.state['equity']:.2f}")
        table.add_row("Net PnL", f"{self.state['net_pnl']:.2f}")
        table.add_row("Trades", str(self.state["trades"]))
        table.add_row("Wins / Losses", f"{self.state['wins']} / {self.state['losses']}")
        table.add_row("Win rate", self.state["win_rate"])
        table.add_row("Open trade", self.state["open_trade"])

        return table

    def _build_events_table(self):
        table = Table(
            title="Recent Events",
            box=box.SIMPLE,
            expand=True,
        )
        table.add_column("Time", style="dim", no_wrap=True)
        table.add_column("Level", style="bold", no_wrap=True)
        table.add_column("Message", overflow="fold")

        if not self.events:
            table.add_row("-", "-", "No events yet")
            return table

        for timestamp, level, message in self.events:
            level_style = {
                "START": "green",
                "PHASE": "cyan",
                "PAUSE": "yellow",
                "ERROR": "bold red",
                "RESUME": "magenta",
                "CHECKPOINT": "yellow",
                "DONE": "bold green",
            }.get(level, "white")
            table.add_row(timestamp, f"[{level_style}]{level}[/{level_style}]", message)

        return table

    def _build_renderable(self):
        return Group(
            self._build_header(),
            Panel(self.progress, title="Progress", expand=True),
            self._build_status_table(),
            self._build_events_table(),
        )

    def refresh(self):
        if self.enabled and self.live is not None:
            self.live.update(self._build_renderable(), refresh=True)
