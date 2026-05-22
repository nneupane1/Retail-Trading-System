"""Rich-based live console display for historical downloads."""

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


class DownloadProgressDisplay:
    """
    Live download progress UI for the terminal.
    """

    def __init__(self, enabled=True):
        self.enabled = enabled and RICH_AVAILABLE
        self.console = Console() if self.enabled else None
        self.live = None
        self.progress = None
        self.task_id = None
        self.events = deque(maxlen=8)
        self.state = {}

    def start(
        self,
        symbol,
        interval,
        start_date,
        end_date,
        final_path,
        checkpoint_path,
        resumed=False,
        resume_point=None,
        total_rows=0,
        initial_progress_pct=0.0,
        verify_mode="enabled",
    ):
        if not self.enabled:
            return

        self.state = {
            "symbol": symbol,
            "interval": interval,
            "start_date": start_date,
            "end_date": end_date,
            "final_path": str(final_path),
            "checkpoint_path": str(checkpoint_path),
            "phase": "Preparing download",
            "current_batch": "-",
            "current_window": "-",
            "batch_rows": "-",
            "total_rows": total_rows,
            "progress_pct": initial_progress_pct,
            "remaining_pct": max(0.0, 100.0 - initial_progress_pct),
            "elapsed": "0s",
            "eta": "-",
            "resume_point": resume_point or "-",
            "verify_mode": verify_mode,
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
            f"Downloading {symbol} {interval} history",
            total=100,
            completed=initial_progress_pct,
        )

        self.live = Live(
            self._build_renderable(),
            console=self.console,
            refresh_per_second=6,
            transient=False,
        )
        self.live.start()

        if resumed:
            self.add_event(
                "resume",
                f"Resuming from {resume_point} with {total_rows} stored rows",
            )
            self.state["phase"] = "Resuming download"
        else:
            self.add_event("start", "Starting from the beginning")
            self.state["phase"] = "Starting download"

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

    def update_request(self, batch_number, request_from, limit):
        if not self.enabled:
            return

        self.state["phase"] = "Requesting batch"
        self.state["current_batch"] = batch_number
        self.state["current_window"] = f"from {request_from}"
        self.state["batch_rows"] = f"limit {limit}"
        self.refresh()

    def update_retry(self, attempt, total_attempts, delay, reason):
        if not self.enabled:
            return

        self.state["phase"] = f"Retrying request ({attempt}/{total_attempts})"
        self.add_event(
            "retry",
            f"Retry in {delay:.2f}s after: {self._truncate(reason, 90)}",
        )

    def update_batch_result(
        self,
        batch_number,
        window_start,
        window_end,
        batch_rows,
        total_rows,
        progress_pct,
        remaining_pct,
        elapsed_seconds,
        eta_seconds,
        resume_point,
    ):
        if not self.enabled:
            return

        self.state["phase"] = "Batch saved"
        self.state["current_batch"] = batch_number
        self.state["current_window"] = f"{window_start} -> {window_end}"
        self.state["batch_rows"] = batch_rows
        self.state["total_rows"] = total_rows
        self.state["progress_pct"] = progress_pct
        self.state["remaining_pct"] = remaining_pct
        self.state["elapsed"] = _fmt_duration(elapsed_seconds)
        self.state["eta"] = _fmt_duration(eta_seconds)
        self.state["resume_point"] = resume_point

        self.progress.update(self.task_id, completed=progress_pct)
        self.add_event(
            "saved",
            f"Batch {batch_number} saved | {batch_rows} rows | total {total_rows}",
        )

    def update_waiting(self, throttle_seconds):
        if not self.enabled:
            return

        self.state["phase"] = f"Waiting {throttle_seconds:.2f}s before next request"
        self.refresh()

    def update_finalizing(self):
        if not self.enabled:
            return

        self.state["phase"] = "Finalizing CSV"
        self.add_event("finalize", "Download loop complete, writing final CSV")

    def update_completed(self, total_rows, total_time_seconds, final_path):
        if not self.enabled:
            return

        self.state["phase"] = "Completed"
        self.state["total_rows"] = total_rows
        self.state["elapsed"] = _fmt_duration(total_time_seconds)
        self.state["eta"] = "0s"
        self.state["progress_pct"] = 100.0
        self.state["remaining_pct"] = 0.0
        self.progress.update(self.task_id, completed=100)
        self.add_event("done", f"Saved final CSV -> {final_path}")

    def update_interrupted(self, reason, checkpoint_path):
        if not self.enabled:
            return

        self.state["phase"] = "Interrupted"
        message = "Interrupted by user" if not str(reason) else str(reason)
        self.add_event(
            "stop",
            f"{self._truncate(message, 90)} | checkpoint {checkpoint_path}",
        )

    def _truncate(self, text, max_length):
        text = str(text)
        if len(text) <= max_length:
            return text
        return f"{text[:max_length - 3]}..."

    def _build_status_table(self):
        table = Table(
            title="Download Status",
            box=box.SIMPLE_HEAVY,
            expand=True,
            show_header=False,
        )
        table.add_column("Field", style="bold cyan", no_wrap=True)
        table.add_column("Value", style="white")

        table.add_row("Phase", str(self.state["phase"]))
        table.add_row("Batch", str(self.state["current_batch"]))
        table.add_row("Window", str(self.state["current_window"]))
        table.add_row("Batch rows", str(self.state["batch_rows"]))
        table.add_row("Total rows", f"{self.state['total_rows']:,}")
        table.add_row(
            "Progress",
            f"{self.state['progress_pct']:.2f}% complete "
            f"({self.state['remaining_pct']:.2f}% remaining)",
        )
        table.add_row("Elapsed", self.state["elapsed"])
        table.add_row("ETA", self.state["eta"])
        table.add_row("Resume point", str(self.state["resume_point"]))
        table.add_row("TLS verify", str(self.state["verify_mode"]))
        table.add_row("Final CSV", self.state["final_path"])
        table.add_row("Checkpoint", self.state["checkpoint_path"])

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
                "RESUME": "yellow",
                "RETRY": "bold yellow",
                "SAVED": "green",
                "FINALIZE": "cyan",
                "DONE": "bold green",
                "STOP": "bold red",
            }.get(level, "white")
            table.add_row(timestamp, f"[{level_style}]{level}[/{level_style}]", message)

        return table

    def _build_header(self):
        title = f"[bold]Historical Download[/bold]  [cyan]{self.state['symbol']}[/cyan]  [magenta]{self.state['interval']}[/magenta]"
        subtitle = f"{self.state['start_date']} -> {self.state['end_date']}"
        return Panel(title, title="Retail Trading System", subtitle=subtitle, expand=True)

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
