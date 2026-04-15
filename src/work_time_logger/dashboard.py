"""Dashboard screen for visualizing work statistics."""

from datetime import datetime, timedelta

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Static

from . import operations


class DashboardScreen(Screen):
    """A screen that displays aggregated work statistics and charts."""

    CSS = """
    DashboardScreen {
        background: $surface;
    }
    #dashboard-container {
        padding: 1 2;
    }
    .section-title {
        text-style: bold;
        background: $primary;
        color: $text;
        padding: 0 1;
        margin-bottom: 1;
    }
    .stats-card {
        border: solid $accent;
        padding: 1;
        margin: 1;
        height: auto;
    }
    #period-selector {
        height: 3;
        margin-bottom: 1;
    }
    .period-btn {
        margin-right: 2;
    }
    """

    BINDINGS = [
        Binding("d", "app.pop_screen", "Back to Logs"),
        Binding("escape", "app.pop_screen", "Back to Logs"),
        Binding("w", "set_period('week')", "This Week"),
        Binding("m", "set_period('month')", "This Month"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.period = "week"  # "week" or "month"

    def compose(self) -> ComposeResult:
        """Compose the dashboard screen widgets.

        Returns:
            ComposeResult: The standard Textual compose result.
        """
        yield Header()
        with Container(id="dashboard-container"):
            with Horizontal(id="period-selector"):
                yield Button(
                    "Weekly (W)", id="btn-week", variant="primary", classes="period-btn"
                )
                yield Button("Monthly (M)", id="btn-month", classes="period-btn")

            with Vertical():
                yield Static("Project Distribution", classes="section-title")
                yield DataTable(id="project-stats-table")

                yield Static("Daily Activity", classes="section-title")
                yield Static(id="activity-chart")
        yield Footer()

    def on_mount(self) -> None:
        """Dashboard screen mount handler. Triggers the initial data fetch."""
        self.update_dashboard()

    def action_set_period(self, period: str) -> None:
        """Switch the dashboard view between weekly and monthly periods.

        Args:
            period (str): Either 'week' or 'month'.
        """
        self.period = period
        # Update button styles
        self.query_one("#btn-week").variant = (
            "primary" if period == "week" else "default"
        )
        self.query_one("#btn-month").variant = (
            "primary" if period == "month" else "default"
        )
        self.update_dashboard()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events to switch the display period.

        Args:
            event (Button.Pressed): The button press event.
        """
        if event.button.id == "btn-week":
            self.action_set_period("week")
        elif event.button.id == "btn-month":
            self.action_set_period("month")

    def update_dashboard(self) -> None:
        """Fetch data and update all dashboard components.

        Calculates:
        1. Start/End dates for the selected period (week or month).
        2. Filtered logs for that period.
        3. Project hour totals and percentages.
        4. Daily aggregated totals for the activity chart.

        Updates the project distribution table and the ASCII sparkline chart.
        """
        logs = operations.list_logs()
        now = datetime.now()

        if self.period == "week":
            # Start of current week (Monday)
            start_date = (now - timedelta(days=now.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            days_count = 7
        else:
            # Start of current month
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # Find last day of month
            if now.month == 12:
                next_month = now.replace(year=now.year + 1, month=1, day=1)
            else:
                next_month = now.replace(month=now.month + 1, day=1)
            days_count = (next_month - start_date).days

        # Filter logs by period
        period_logs = []
        for log in logs:
            dt = datetime.fromisoformat(log["start_time"])
            if dt >= start_date:
                period_logs.append(log)

        # 1. Project Stats Table
        table = self.query_one("#project-stats-table", DataTable)
        table.clear()
        if not table.columns:
            table.add_columns("Project", "Hours", "Percentage", "Bar")

        project_totals = {}
        total_period_hours = 0.0
        for log in period_logs:
            p = log["project_name"] or "[未割り当て]"
            h = log["duration_hours"]
            if h is None and log["end_time"]:
                s = datetime.fromisoformat(log["start_time"])
                e = datetime.fromisoformat(log["end_time"])
                h = (e - s).total_seconds() / 3600.0
            h = h or 0.0
            project_totals[p] = project_totals.get(p, 0.0) + h
            total_period_hours += h

        sorted_projects = sorted(
            project_totals.items(), key=lambda x: x[1], reverse=True
        )
        for p, h in sorted_projects:
            pct = (h / total_period_hours * 100) if total_period_hours > 0 else 0
            bar = "█" * int(pct / 5)
            table.add_row(
                Text(str(p)),
                Text(f"{h:.2f}"),
                Text(f"{pct:.1f}%"),
                Text(bar, style="#79a8a8"),
            )

        # 2. Daily Activity Chart (Simple ASCII)
        chart_static = self.query_one("#activity-chart", Static)
        daily_totals = [0.0] * days_count
        for log in period_logs:
            dt = datetime.fromisoformat(log["start_time"])
            day_idx = (dt - start_date).days
            if 0 <= day_idx < days_count:
                h = log["duration_hours"]
                if h is None and log["end_time"]:
                    s = datetime.fromisoformat(log["start_time"])
                    e = datetime.fromisoformat(log["end_time"])
                    h = (e - s).total_seconds() / 3600.0
                daily_totals[day_idx] += h or 0.0

        chart_lines = []
        # Header with dates
        header = "Day: "
        for i in range(days_count):
            d = start_date + timedelta(days=i)
            header += f"{d.day:2} "
        chart_lines.append(header)

        # Simple Sparkline-like representation
        spark = "Hrs: "
        for h in daily_totals:
            if h == 0:
                spark += " . "
            elif h < 2:
                spark += " ▂ "
            elif h < 4:
                spark += " ▃ "
            elif h < 6:
                spark += " ▅ "
            else:
                spark += " █ "
        chart_lines.append(spark)

        # Data values
        vals = "Val: "
        for h in daily_totals:
            vals += f"{int(h):2} "
        chart_lines.append(vals)

        chart_static.update("\n".join(chart_lines))
