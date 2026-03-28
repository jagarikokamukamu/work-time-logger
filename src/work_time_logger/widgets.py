"""Custom widgets and modals for the Work Time Logger TUI."""

from datetime import datetime, timedelta

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

from . import db, operations


class CopyableDataTable(DataTable):
    """A DataTable that supports copying the selected row or cell to the clipboard."""

    BINDINGS = [
        Binding("c", "copy_to_clipboard", "コピー", show=True),
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
            self.app.notify("クリップボードにコピーしました", title="Copied")
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


class DailySummaryModal(ModalScreen):
    """A modal screen that displays an aggregated summary of work per day."""

    CSS = """
    DailySummaryModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #summary-container {
        width: 90%;
        height: 80%;
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
    .copy-hint {
        content-align: right middle;
        width: 100%;
        text-style: italic;
        opacity: 0.8;
        margin-top: 1;
    }
    """

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the summary screen widgets."""
        with Container(id="summary-container"):
            yield Static("Daily Work Summary", classes="summary-title")
            yield CopyableDataTable(id="summary-table")
            yield Label("[b orange]c[/] copy", classes="copy-hint")

    def on_mount(self) -> None:
        """Mount handler to populate the summary table."""
        from . import exporter
       
        table = self.query_one(CopyableDataTable)
       
        try:
            from rich.text import Text
            profile_path = str(db.DB_DIR / "profile.toml")
            columns_config, aggregated_results = exporter.aggregate_logs(
                profile_path, target_date=None, group_by_date=True
            )
           
            # Setup columns: Date + configured CSV columns
            col_names = ["Date"] + list(columns_config.keys())
            table.add_columns(*[Text(c) for c in col_names])
           
            for row in aggregated_results:
                row_values = [Text(str(row.get("_date", "")))]
                for col in columns_config.keys():
                    row_values.append(Text(str(row.get(col, ""))))
                table.add_row(*row_values)
                
        except Exception as e:
            table.add_columns("Error")
            table.add_row(f"Failed to load summary: {e}")
            
        table.focus()


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
    """

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
    ]

    def __init__(self, project_name: str, job_name: str, **kwargs):
        super().__init__(**kwargs)
        self.project_name = project_name
        self.job_name = job_name

    def compose(self) -> ComposeResult:
        """Compose the job code expansion screen widgets."""
        with Container(id="job-code-container"):
            yield Static(
                f"Job Code Expansion: {self.job_name}", classes="job-code-title"
            )
            yield CopyableDataTable(id="job-code-table")
            yield Label("[b orange]c[/] copy", classes="copy-hint")
            yield Button("Close", id="btn-close", variant="primary")

    def on_mount(self) -> None:
        """Mount handler to populate the job code table."""
        from . import exporter

        table = self.query_one(CopyableDataTable)
        table.add_columns("Column", "Value")

        try:
            profile_path = db.DB_DIR / "profile.toml"
            profile_cfg = exporter.load_profile(str(profile_path))
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
                    table.add_row(col_name, value)
            else:
                table.add_row("Error", "Job not found")
        except Exception as e:
            table.add_row("Error", str(e))
        table.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "btn-close":
            self.dismiss()
