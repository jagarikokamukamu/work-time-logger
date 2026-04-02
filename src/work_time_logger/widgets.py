"""Custom widgets and modals for the Work Time Logger TUI."""

from datetime import datetime, timedelta

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    OptionList,
    Static,
)
from textual.widgets.option_list import Option

from . import db, exporter, operations


class CopyableDataTable(DataTable):
    """A DataTable that supports copying the selected row or cell to the clipboard."""

    BINDINGS = [
        Binding("c", "copy_to_clipboard", "コピー", show=True),
        Binding("enter", "select_cursor", "編集", show=True),
    ]

    def action_copy_to_clipboard(self) -> None:
        """Copies the currently selected item to the clipboard."""
        coord = self.cursor_coordinate
        if not coord:
            return

        try:
            if self.cursor_type == "row":
                row_key = self.coordinate_to_cell_key(coord).row_key
                row_vals = self.get_row(row_key)
                text = "\t".join(str(v) for v in row_vals)
            elif self.cursor_type == "column":
                col_key = self.coordinate_to_cell_key(coord).column_key
                col_vals = self.get_column(col_key)
                text = "\n".join(str(v) for v in col_vals)
            else:
                val = self.get_cell_at(coord)
                text = str(val)

            self.app.copy_to_clipboard(text)
        except Exception as e:
            self.app.notify(f"コピーに失敗しました: {e}", severity="error")


class JobSelectionModal(ModalScreen[tuple[str, str]]):
    """Modal to fuzzy search and select a job to start."""

    CSS = """
    JobSelectionModal {
        align: center middle;
    }
    #dialog {
        grid-size: 1 2;
        grid-rows: 3 1fr;
        width: 60;
        height: 20;
        border: thick $background 80%;
        background: $surface;
    }
    #search {
        margin: 1 2;
    }
    #job-list {
        margin: 0 2 1 2;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel Job Selection"),
    ]

    def __init__(self):
        super().__init__()
        self.jobs = []
        for p in operations.list_projects():
            for j in operations.list_jobs(p["name"]):
                self.jobs.append((p["name"], j["name"]))

    def compose(self) -> ComposeResult:
        """Compose the child widgets for the modal."""
        yield Container(
            Input(placeholder="Type to search for a job...", id="search"),
            OptionList(id="job-list"),
            id="dialog",
        )

    def on_mount(self) -> None:
        """Mount handler to initialize the option list."""
        self.update_options("")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input change events to filter the job list."""
        self.update_options(event.value)

    def update_options(self, search_term: str) -> None:
        """Filter the job options based on a search term."""
        option_list = self.query_one(OptionList)
        option_list.clear_options()
        term = search_term.lower()
        for i, (p_name, j_name) in enumerate(self.jobs):
            label = f"{j_name} ({p_name})"
            if term in label.lower():
                option_list.add_option(Option(prompt=label, id=str(i)))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle selection of a job from the option list."""
        if event.option_id is not None:
            idx = int(event.option_id)
            selected_project, selected_job = self.jobs[idx]
            self.dismiss((selected_project, selected_job))

    def action_cancel(self) -> None:
        """Dismiss the modal without selection."""
        self.dismiss(None)


class ConfirmDeleteModal(ModalScreen[bool]):
    """Modal to confirm log deletion."""

    CSS = """
    ConfirmDeleteModal {
        align: center middle;
        background: transparent;
    }
    #confirm-dialog {
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 3;
        padding: 0 1;
        width: 50;
        height: 11;
        border: thick $background 80%;
        background: $surface;
    }
    #question {
        column-span: 2;
        height: 1fr;
        width: 1fr;
        content-align: center middle;
    }
    Button {
        width: 100%;
    }
    """

    BINDINGS = [
        ("y", "yes", "Yes"),
        ("n", "no", "No"),
        ("escape", "no", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the confirmation dialog widgets."""
        yield Container(
            Label("Are you sure you want to delete this log?", id="question"),
            Button("Yes (y)", variant="error", id="yes"),
            Button("No (n)", variant="primary", id="no"),
            id="confirm-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events (Yes/No)."""
        if event.button.id == "yes":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_yes(self) -> None:
        """Action handler for 'Yes' response."""
        self.dismiss(True)

    def action_no(self) -> None:
        """Action handler for 'No' response."""
        self.dismiss(False)


class OverlayInput(Input):
    """An input field that overlays a DataTable cell for in-place editing."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("up", "increment", "Increment D/T"),
        ("down", "decrement", "Decrement D/T"),
        ("enter", "submit", "Save"),  # For footer display
        ("tab", "cancel", "Cancel"),
        ("shift+tab", "cancel", "Cancel"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.edit_mode = "memo"  # "memo", "date_only", "time_only", "duration"
        self.duration_step = 0.1

    def action_cancel(self) -> None:
        """Dismiss and hide the overlay input."""
        self.can_focus = False
        self.styles.display = "none"
        # If we are in a modal, we might want to focus the modal's table.
        # Otherwise, default to the main app table.
        try:
            self.screen.query_one(DataTable).focus()
        except Exception:
            self.app.query_one(DataTable).focus()

    def action_increment(self) -> None:
        """Increment the current field value."""
        self._adjust_value(1)

    def action_decrement(self) -> None:
        """Decrement the current field value."""
        self._adjust_value(-1)

    def _adjust_value(self, delta: int) -> None:
        """Adjust the current input value based on the edit mode and delta.

        This handles incrementing/decrementing dates, times, and durations
        using arrow keys.

        Args:
            delta (int): The amount to adjust (typically 1 or -1).
        """
        if self.edit_mode == "memo":
            return

        cursor_pos = self.cursor_position
        val = self.value

        try:
            if self.edit_mode == "date_only":
                # YYYY-MM-DD
                dt = datetime.strptime(val, "%Y-%m-%d")
                if cursor_pos <= 4:
                    dt = dt.replace(year=max(1, dt.year + delta))
                elif cursor_pos <= 7:
                    # Move month
                    month = dt.month + delta
                    year = dt.year
                    while month > 12:
                        month -= 12
                        year += 1
                    while month < 1:
                        month += 12
                        year -= 1
                    # Ensure day is valid for new month
                    import calendar

                    last_day = calendar.monthrange(year, month)[1]
                    dt = dt.replace(year=year, month=month, day=min(dt.day, last_day))
                else:
                    dt += timedelta(days=delta)
                self.value = dt.strftime("%Y-%m-%d")

            elif self.edit_mode == "time_only":
                # HH:mm:ss or YYYY-MM-DD HH:mm:ss
                if "T" in val:
                    val = val.replace("T", " ")
                if " " in val:
                    # Parse full ISO
                    dt = datetime.fromisoformat(val)
                    if cursor_pos <= 10:  # Date part
                        dt += timedelta(days=delta)
                    elif cursor_pos <= 13:  # HH
                        dt += timedelta(hours=delta)
                    elif cursor_pos <= 16:  # mm
                        dt += timedelta(minutes=delta)
                    else:  # ss
                        dt += timedelta(seconds=delta)
                    self.value = dt.isoformat(sep=" ")
                else:
                    # Simple HH:mm
                    parts = val.split(":")
                    if len(parts) != 2:
                        return
                    try:
                        h, m = int(parts[0]), int(parts[1])
                        if cursor_pos <= len(parts[0]):
                            h += delta
                        else:
                            m += delta

                        total_mins = h * 60 + m
                        total_mins = max(0, total_mins)
                        nh, nm = divmod(total_mins, 60)
                        self.value = f"{nh:02}:{nm:02}"
                    except ValueError:
                        pass

            elif self.edit_mode == "duration":
                # Float hours, increment by duration_step
                try:
                    curr_val = float(val) if val.strip() else 0.0
                    new_val = max(0.0, curr_val + (delta * self.duration_step))
                    # Round to 2 decimal places to avoid float precision issues
                    self.value = str(round(new_val, 2))
                except ValueError:
                    pass

            elif self.edit_mode == "date":  # Legacy fallback
                dt = datetime.fromisoformat(val)
                dt += timedelta(seconds=delta)
                self.value = dt.isoformat(sep=" ")

            self.cursor_position = cursor_pos
        except (ValueError, TypeError, AttributeError):
            # Ignore transient UI errors during rapid cursor/value adjustment.
            pass


class HelpModal(ModalScreen):
    """A modal screen that displays a list of all commands."""

    CSS = """
    HelpModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #help-container {
        width: 70;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }
    .help-title {
        content-align: center middle;
        width: 100%;
        text-style: bold;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the help screen contents."""
        with Container(id="help-container"):
            yield Static("WTL Keyboard Shortcuts", classes="help-title")
            yield Static(
                "Global Commands:\n"
                "  h, f1   : Show this detailed help message\n"
                "  tab     : Switch focus between Sidebar and Main Content\n"
                "  q       : Quit application\n"
                "  s       : Search / Start a new job\n"
                "  shift+s : Start unassigned timer\n"
                "  shift+a : Add empty log\n"
                "  x       : Stop tracking current job\n"
                "  e       : Export logs to CSV\n"
                "  v       : View Daily Summary (aggregates hours)\n"
                "  d       : View Dashboard (Weekly/Monthly charts)\n"
                "  f       : Filter logs by Project, Job, or Date Range\n"
                "\nSidebar Focus (Projects & Jobs):\n"
                "  enter   : Start selected job\n"
                "  a       : Add log pre-assigned to selected job\n"
                "\nMain List Focus (Logs):\n"
                "  enter   : Edit selected cell (Date, Time, Memo, or Duration)\n"
                "  shift+d : Delete selected log\n"
                "  r       : Restart (clone) selected job\n"
                "\nEdit Mode:\n"
                "  enter   : Save changes\n"
                "  esc     : Cancel edit\n"
                "  up/down : Adjust values for date/time fields"
            )

    def on_key(self, event) -> None:
        """Dismiss the modal on any key press."""
        self.dismiss()


class ExportLogsModal(ModalScreen[tuple[str, str, str]]):
    """Modal to enter file paths and date for exporting logs."""

    CSS = """
    ExportLogsModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #export-dialog {
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 1fr 1fr 1fr;
        padding: 1 2;
        width: 60;
        height: 22;
        border: thick $background 80%;
        background: $surface;
    }
    .export-label {
        column-span: 2;
        height: 1fr;
        content-align: left bottom;
    }
    #export-profile, #export-output, #export-date {
        column-span: 2;
    }
    .dialog-buttons {
        width: 100%;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the export dialog widgets."""
        from datetime import date

        yield Container(
            Label("Profile (.toml):", classes="export-label"),
            Input(value=str(db.DB_DIR / "profile.toml"), id="export-profile"),
            Label("Date (YYYY-MM-DD, or 'all'):", classes="export-label"),
            Input(value=date.today().isoformat(), id="export-date"),
            Label("Output CSV Path:", classes="export-label"),
            Input(value="report.csv", id="export-output"),
            Button(
                "Export", variant="success", id="btn-export", classes="dialog-buttons"
            ),
            Button(
                "Cancel", variant="error", id="btn-cancel", classes="dialog-buttons"
            ),
            id="export-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle export or cancel button presses."""
        if event.button.id == "btn-export":
            profile = self.query_one("#export-profile", Input).value.strip()
            output = self.query_one("#export-output", Input).value.strip()
            date_val = self.query_one("#export-date", Input).value.strip()
            if profile and output:
                self.dismiss((profile, output, date_val))
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        """Dismiss the modal."""
        self.dismiss(None)


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


class TimelineVisualizer(Static):
    """A widget that visualizes work intervals on a 0-24h timeline."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.intervals = []  # List of (start_iso, end_iso, color)

    def set_intervals(self, intervals: list[tuple[str, str, str]]) -> None:
        """Update the intervals to display."""
        self.intervals = intervals
        self.refresh()

    def render(self) -> Text:
        """Render the 24-hour timeline bar."""
        # 0 to 24 hours, 2 characters per hour = 48 chars wide
        bar_width = 48
        text = Text(" " * bar_width, style="on #2e2e2e")

        for start_iso, end_iso, color in self.intervals:
            if not start_iso or not end_iso:
                continue
            try:
                s = datetime.fromisoformat(start_iso)
                e = datetime.fromisoformat(end_iso)

                # Map time to 0.0-24.0 range
                start_f = s.hour + s.minute / 60.0 + s.second / 3600.0
                end_f = e.hour + e.minute / 60.0 + e.second / 3600.0

                start_idx = int(start_f * (bar_width / 24.0))
                end_idx = int(end_f * (bar_width / 24.0))

                # Highlight the range
                style = f"on {color}" if color else "on #79a8a8"
                if end_idx > start_idx:
                    text.stylize(style, start_idx, end_idx)
                elif end_idx == start_idx and start_idx < bar_width:
                    text.stylize(style, start_idx, start_idx + 1)
            except (ValueError, TypeError):
                continue

        ruler_str = (
            "0" + " " * 10 + "6" + " " * 11 + "12" + " " * 11 + "18" + " " * 9 + "24"
        )
        ruler = Text("\n" + ruler_str, style="#585858")
        return text + ruler


class DailySummaryModal(ModalScreen):
    """A modal screen that displays an aggregated summary of work per day."""

    CSS = """
    DailySummaryModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #summary-container {
        width: 80;
        height: 32;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }
    .summary-title {
        content-align: center middle;
        width: 100%;
        text-style: bold;
        margin-bottom: 1;
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
        height: 4;
        margin-top: 1;
        content-align: center middle;
    }
    #summary-table {
        height: 1fr;
        margin-top: 1;
    }
    .copy-hint {
        content-align: right middle;
        width: 100%;
        text-style: italic;
        opacity: 0.8;
        margin-top: 1;
    }
    #date-input-overlay {
        display: none;
        width: 100%;
        height: 100%;
        background: $boost;
        color: yellow;
        text-style: bold;
        border: none;
        content-align: center middle;
    }
    """

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
        ("left", "prev_day", "Prev Day"),
        ("right", "next_day", "Next Day"),
        ("[", "prev_day", "Prev Day"),
        ("]", "next_day", "Next Day"),
        ("C", "copy_report", "Copy Report"),
        ("/", "show_date_input", "Jump to Date"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.target_date = datetime.now().strftime("%Y-%m-%d")

    def compose(self) -> ComposeResult:
        """Compose the summary screen widgets."""
        with Container(id="summary-container"):
            yield Static("Daily Work Summary", classes="summary-title")
            with Horizontal(id="summary-header"):
                yield Static(self.target_date, id="header-date-text")
                yield Static("", id="header-info-text")
                yield Input(placeholder="YYYY-MM-DD", id="date-input-overlay")

            yield TimelineVisualizer(id="summary-visualizer")
            yield CopyableDataTable(id="summary-table")
            yield Label(
                r"[b orange]c[/] copy  [b orange]C[/] copy report  "
                r"[b orange]\[[/] [b orange]][/] navigate  [b orange]/[/] jump",
                classes="copy-hint",
            )

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
        """Show the date input field for direct jumping."""
        self.query_one("#header-date-text").styles.display = "none"
        self.query_one("#header-info-text").styles.display = "none"
        inp = self.query_one("#date-input-overlay", Input)
        inp.value = self.target_date
        inp.styles.display = "block"
        inp.focus()

    @on(Input.Submitted, "#date-input-overlay")
    def on_date_submitted(self, event: Input.Submitted) -> None:
        """Handle date input submission."""
        event.stop()
        val = event.value.strip()
        smart_date = operations.parse_smart_date(val)

        if smart_date:
            self.target_date = smart_date
            self.refresh_summary()
            self._close_date_input()
        else:
            self.app.notify(f"Invalid date: {val}", severity="error")

    def _close_date_input(self) -> None:
        """Hide the date input and return focus to the table."""
        self.query_one("#date-input-overlay", Input).styles.display = "none"
        self.query_one("#header-date-text").styles.display = "block"
        self.query_one("#header-info-text").styles.display = "block"
        self.query_one("#summary-table").focus()

    def on_key(self, event) -> None:
        """Handle specific keys in the modal, especially for cancelling input."""
        if event.key == "escape":
            inp = self.query_one("#date-input-overlay", Input)
            if inp.styles.display == "block":
                event.stop()
                self._close_date_input()
                return
        # Allow default ModalScreen behavior if not handled


class FilterModal(ModalScreen):
    """A modal screen for filtering logs by project, job, and date range."""

    CSS = """
    FilterModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #filter-container {
        width: 60;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }
    .filter-label {
        margin-top: 1;
        text-style: bold;
    }
    .filter-buttons {
        margin-top: 2;
        height: 3;
        align: right middle;
    }
    .filter-btn {
        margin-left: 1;
    }
    """

    def __init__(self, current_filters: dict, **kwargs):
        super().__init__(**kwargs)
        self.current_filters = current_filters

    def compose(self) -> ComposeResult:
        """Compose the filter dialog widgets."""
        with Container(id="filter-container"):
            yield Static("Filter Logs", classes="summary-title")

            yield Static("Project Name:", classes="filter-label")
            yield Input(
                value=self.current_filters.get("project") or "",
                id="f-project",
                placeholder="None",
            )

            yield Static("Job Name:", classes="filter-label")
            yield Input(
                value=self.current_filters.get("job") or "",
                id="f-job",
                placeholder="None",
            )

            yield Static("Start Date (YYYY-MM-DD):", classes="filter-label")
            yield Input(
                value=self.current_filters.get("start") or "",
                id="f-start",
                placeholder="None",
            )

            yield Static("End Date (YYYY-MM-DD):", classes="filter-label")
            yield Input(
                value=self.current_filters.get("end") or "",
                id="f-end",
                placeholder="None",
            )

            with Horizontal(classes="filter-buttons"):
                yield Button(
                    "Clear", id="btn-clear", variant="error", classes="filter-btn"
                )
                yield Button("Cancel", id="btn-cancel", classes="filter-btn")
                yield Button(
                    "Apply", id="btn-apply", variant="primary", classes="filter-btn"
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle filter dialog button presses."""
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-clear":
            self.dismiss({"project": None, "job": None, "start": None, "end": None})
        elif event.button.id == "btn-apply":
            res = {
                "project": self.query_one("#f-project", Input).value.strip() or None,
                "job": self.query_one("#f-job", Input).value.strip() or None,
                "start": self.query_one("#f-start", Input).value.strip() or None,
                "end": self.query_one("#f-end", Input).value.strip() or None,
            }
            self.dismiss(res)


class JobCodeModal(ModalScreen):
    """A modal screen that displays the job code expansion for a specific job."""

    CSS = """
    JobCodeModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #job-code-container {
        width: 80;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }
    .job-code-title {
        content-align: center middle;
        width: 100%;
        text-style: bold;
        margin-bottom: 1;
    }
    .copy-hint {
        content-align: right middle;
        width: 100%;
        text-style: italic;
        opacity: 0.8;
        margin-top: 1;
        margin-bottom: 1;
    }
    #job-code-table {
        height: auto;
        max-height: 20;
    }
    #btn-close {
        margin-top: 1;
        width: 100%;
    }
    #edit-section {
        margin-top: 1;
        display: none;
        height: auto;
        border: tall $accent;
        padding: 0 1;
    }
    #edit-label {
        width: 20;
        content-align: left middle;
        text-style: bold;
    }
    #job-code-edit-input {
        width: 1fr;
    }
    """

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
        ("t", "toggle_mode", "Toggle Export/Import"),
    ]

    def __init__(self, project_name: str, job_name: str, **kwargs):
        super().__init__(**kwargs)
        self.project_name = project_name
        self.job_name = job_name
        self.mode = "export"  # "export" or "import"
        self.import_row = {}
        self.name_vars = []
        self._editing_col_name = None

    def compose(self) -> ComposeResult:
        """Compose the job code expansion screen widgets."""
        with Container(id="job-code-container"):
            yield Static(id="job-code-title", classes="job-code-title")
            yield CopyableDataTable(id="job-code-table", cursor_type="cell")
            yield Label("[b orange]c[/] copy  [b blue]t[/] toggle", classes="copy-hint")
            with Horizontal(id="edit-section"):
                yield Label("Edit:", id="edit-label")
                yield Input(id="job-code-edit-input")
            yield Button("Close", id="btn-close", variant="primary")

    def on_mount(self) -> None:
        """Mount handler to populate the job code table."""
        self.refresh_table()

    def action_toggle_mode(self) -> None:
        """Toggle between Export and Import display modes."""
        # Reset UI state when switching modes
        self.query_one("#edit-section").styles.display = "none"
        self.mode = "import" if self.mode == "export" else "export"
        self.refresh_table()

    def refresh_table(self) -> None:
        """Update the table content based on the current mode."""
        table = self.query_one(CopyableDataTable)
        table.clear(columns=True)
        table.add_columns("Column", "Value")

        title = self.query_one("#job-code-title", Static)
        mode_label = "(Export Mode)" if self.mode == "export" else "(Import Mode)"
        title.update(
            f"Job Code Expansion: {self.job_name} [#79a8a8]{mode_label}[/#79a8a8]"
        )

        try:
            if self.mode == "export":
                self._refresh_export_mode(table)
            else:
                self._refresh_import_mode(table)
        except Exception as e:
            table.add_row("Error", str(e))
        table.focus()

    def _refresh_export_mode(self, table: DataTable) -> None:
        """Loads and renders job expansion for export."""
        profile_path = str(db.DB_DIR / "profile.toml")
        profile_cfg = exporter.load_profile(profile_path)
        export_config = profile_cfg.get("export", {})
        compiled_regexes = exporter.get_extract_regexes(export_config)
        defaults = export_config.get("defaults", {})
        columns_config = export_config.get("columns", {})

        # Find the job to get its code
        jobs = operations.list_jobs(self.project_name)
        job = next((j for j in jobs if j["name"] == self.job_name), None)
        if job:
            job_code = job["code"] or ""
            ctx = exporter.extract_fields(job_code, compiled_regexes, defaults)
            ctx.update(
                {
                    "project_name": self.project_name,
                    "job_name": self.job_name,
                    "aggregated_time": "",
                    "aggregated_notes": "",
                }
            )
            rendered = exporter.render_columns(columns_config, ctx)
            for col_name, value in rendered.items():
                table.add_row(Text(str(col_name)), Text(str(value)))
        else:
            table.add_row(Text("Error"), Text("Job not found"))

    def _refresh_import_mode(self, table: DataTable) -> None:
        """Loads and renders job attributes for import/edit."""
        profile_path = str(db.DB_DIR / "profile.toml")
        profile_cfg = exporter.load_profile(profile_path)
        _, row, name_vars = exporter.get_job_import_row(
            profile_cfg, self.project_name, self.job_name
        )
        self.import_row = row
        self.name_vars = name_vars
        for col_name, value in row.items():
            if col_name in name_vars:
                continue
            table.add_row(Text(str(col_name)), Text(str(value)), key=col_name)

    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        """Handle cell selection for editing in Import mode."""
        if event.control.id != "job-code-table":
            return
        event.stop()  # Prevent the event from bubbling up to the main App!
        if self.mode != "import":
            return

        # Ensure we are in the "Value" column (index 1)
        if event.coordinate.column != 1:
            return

        row_key = event.cell_key.row_key.value
        if not row_key:
            return

        # Protection: Cannot edit variables that are part of the Job Name
        if row_key in self.name_vars:
            self.app.notify("Job名は編集できません", severity="warning")
            return

        current_value = str(self.import_row.get(row_key, ""))
        self.start_editing(row_key, current_value)

    def start_editing(self, col_name: str, value: str) -> None:
        """Standard stable editing via a fixed input field."""
        self._editing_col_name = col_name

        section = self.query_one("#edit-section", Horizontal)
        label = self.query_one("#edit-label", Label)
        inp = self.query_one("#job-code-edit-input", Input)

        label.update(f"Edit {col_name}:")
        inp.value = value
        section.styles.display = "block"
        inp.focus()

    @on(Input.Submitted, "#job-code-edit-input")
    def on_edit_submitted(self, event: Input.Submitted) -> None:
        """Saves the edited value to the database."""
        event.stop()
        new_value = event.value.strip()
        col_name = self._editing_col_name

        if col_name:
            try:
                profile_path = str(db.DB_DIR / "profile.toml")
                profile = exporter.load_profile(profile_path)

                # Update our local record first to provide full context for rendering
                self.import_row[col_name] = new_value

                exporter.update_job_from_import_row(
                    profile, self.project_name, self.job_name, self.import_row
                )
            except Exception as e:
                self.app.notify(f"Failed to update: {e}", severity="error")

        self.query_one("#edit-section").styles.display = "none"
        self.refresh_table()
        self.query_one("#job-code-table").focus()

    def on_key(self, event) -> None:
        """Handle escape to cancel editing."""
        if event.key == "escape":
            inp = self.query_one("#job-code-edit-input")
            if inp.has_focus:
                event.stop()
                self.query_one("#edit-section").styles.display = "none"
                self.query_one("#job-code-table").focus()
                return
        # Default behavior: ModalScreen handles escape to dismiss if not caught above.

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        event.stop()
        if event.button.id == "btn-close":
            self.dismiss()
