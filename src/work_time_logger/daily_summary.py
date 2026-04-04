"""Daily Summary Screen."""

from datetime import datetime

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from . import db, operations
from .modals.jump_to_date import JumpToDateModal
from .widgets import CopyableDataTable, TimelineVisualizer

SUMMARY_COLORS = [
    "#79a8a8",  # Default Teal
    "#ff5f5f",  # Red
    "#5fff5f",  # Green
    "#5fafff",  # Blue
    "#ffff5f",  # Yellow
    "#af5fff",  # Purple
    "#ffaf5f",  # Orange
    "#5fffff",  # Cyan
    "#ff5fff",  # Pink
    "#d7af00",  # Gold
]


class DailySummaryScreen(Screen):
    """A screen that displays an aggregated summary of work per day."""

    TITLE = "WtlApp > Daily Work Summary"

    CSS = """
    DailySummaryScreen {
        background: $surface;
    }
    #summary-container {
        padding: 1 2;
    }
    #summary-header {
        height: 3;
        margin: 0 1;
        content-align: center middle;
        border: solid $accent;
        background: $boost;
    }
    #header-date-text {
        width: 12;
        text-style: bold;
        color: yellow;
        content-align: center middle;
    }
    #header-info-text {
        width: 1fr;
        content-align: center middle;
    }
    #summary-visualizer {
        height: 2;
        margin-top: 1;
        content-align: center middle;
    }
    #summary-table {
        height: 1fr;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("q", "app.pop_screen", "Back", show=False),
        Binding("v", "app.pop_screen", "Back", show=False),
        Binding("left", "prev_day", "Prev Day"),
        Binding("right", "next_day", "Next Day"),
        Binding("[", "prev_day", "Prev Day", show=False),
        Binding("]", "next_day", "Next Day", show=False),
        Binding("C", "copy_report", "Copy Report"),
        Binding("/", "show_date_input", "Jump to Date"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.target_date = datetime.now().strftime("%Y-%m-%d")

    def compose(self) -> ComposeResult:
        """Compose the summary screen widgets."""
        yield Header()
        with Container(id="summary-container"):
            with Horizontal(id="summary-header"):
                yield Static(self.target_date, id="header-date-text")
                yield Static("", id="header-info-text")

            yield TimelineVisualizer(id="summary-visualizer")
            yield CopyableDataTable(id="summary-table")
        yield Footer()

    def on_mount(self) -> None:
        """Mount handler to populate the summary data."""
        self.refresh_summary()
        self.query_one("#summary-table").focus()

    def refresh_summary(self) -> None:
        """Refresh all summary data for the current target_date."""
        from . import exporter

        table = self.query_one(CopyableDataTable)
        date_text = self.query_one("#header-date-text", Static)
        info_text = self.query_one("#header-info-text", Static)
        viz = self.query_one(TimelineVisualizer)

        date_text.update(self.target_date)
        table.clear(columns=True)

        try:
            profile_path = str(db.DB_DIR / "profile.toml")
            columns_config, aggregated_results = exporter.aggregate_logs(
                profile_path, target_date=self.target_date, group_by_date=False
            )

            if not aggregated_results:
                info_text.update("[yellow]No logs found[/yellow]")
                viz.set_intervals([])
                table.add_columns("Status")
                table.add_row("No data")
                return

            starts = [
                r.get("first_start") for r in aggregated_results if r.get("first_start")
            ]
            ends = [r.get("last_end") for r in aggregated_results if r.get("last_end")]

            first_s = min(starts) if starts else ""
            last_e = max(ends) if ends else ""
            total_h = sum(
                float(r.get("aggregated_time", 0)) for r in aggregated_results
            )

            def fmt_t(iso_str):
                if not iso_str:
                    return "--:--"
                return iso_str[11:16]

            info_text.update(
                f"Start: [b]{fmt_t(first_s)}[/]  End: [b]{fmt_t(last_e)}[/]  "
                f"Total: [#79a8a8][b]{total_h:.2f}h[/b][/#79a8a8]"
            )

            # Update Table
            col_names = list(columns_config.keys())
            table.add_column("●", width=2)
            table.add_columns(*[Text(c) for c in col_names])

            # Color assignment based on group key
            group_to_color = {}
            for i, row in enumerate(aggregated_results):
                group_to_color[row["_group_key"]] = SUMMARY_COLORS[
                    i % len(SUMMARY_COLORS)
                ]

            for row in aggregated_results:
                row_values = []
                color = group_to_color[row["_group_key"]]
                row_values.append(Text("●", style=color))
                for col in col_names:
                    row_values.append(Text(str(row.get(col, ""))))
                table.add_row(*row_values)

            all_logs = operations.list_logs()
            intervals = []

            # For each log, compute its group key to find the corresponding color
            profile = exporter.load_profile(profile_path)
            export_config = profile.get("export", {})
            compiled_regexes = exporter.get_extract_regexes(export_config)
            defaults_config = export_config.get("defaults", {})
            group_by_keys = export_config.get("group_by", [])

            for log in all_logs:
                if (
                    log["start_time"]
                    and log["start_time"][:10] == self.target_date
                    and log["end_time"]
                ):
                    # Compute group key using the same logic as exporter
                    job_code = log["job_code"] or ""
                    row_data = exporter.extract_fields(
                        job_code, compiled_regexes, defaults_config
                    )
                    group_key = tuple(row_data.get(k, "") for k in group_by_keys)

                    color = group_to_color.get(group_key, "#79a8a8")
                    intervals.append((log["start_time"], log["end_time"], color))

            viz.set_intervals(intervals)

        except Exception as e:
            info_text.update(f"[red]Error: {e}[/red]")
            table.add_columns("Error")
            table.add_row(str(e))

    def action_prev_day(self) -> None:
        """Move to the previous day."""
        from datetime import timedelta

        dt = datetime.fromisoformat(self.target_date)
        self.target_date = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
        self.refresh_summary()

    def action_next_day(self) -> None:
        """Move to the next day."""
        from datetime import timedelta

        dt = datetime.fromisoformat(self.target_date)
        self.target_date = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
        self.refresh_summary()

    def action_copy_report(self) -> None:
        """Copy the summary as a formatted text report."""
        table = self.query_one(CopyableDataTable)
        col_names = [str(c.label) for c in table.columns.values()]

        report_lines = [f"Daily Work Report: {self.target_date}", ""]
        for row_key in table.rows:
            row_vals = table.get_row(row_key)
            line_parts = []
            for name, val in zip(col_names, row_vals, strict=False):
                line_parts.append(f"{name}: {val}")
            report_lines.append("- " + " | ".join(line_parts))

        report_text = "\n".join(report_lines)
        self.app.copy_to_clipboard(report_text)

    @on(DataTable.CellSelected, "#summary-table")
    def on_cell_selected(self, event: DataTable.CellSelected) -> None:
        """Stop event bubbling to prevent crashes in the main app."""
        event.stop()

    def action_show_date_input(self) -> None:
        """Show the date input modal for direct jumping."""
        def callback(new_date: str | None) -> None:
            if new_date:
                self.target_date = new_date
                self.refresh_summary()

        self.app.push_screen(JumpToDateModal(self.target_date), callback)
