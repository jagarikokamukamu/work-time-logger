"""Custom widgets and modals for the Work Time Logger TUI."""

from datetime import datetime, timedelta

from textual.app import ComposeResult
from textual.containers import Container
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
        yield Container(
            Input(placeholder="Type to search for a job...", id="search"),
            OptionList(id="job-list"),
            id="dialog",
        )

    def on_mount(self) -> None:
        self.update_options("")

    def on_input_changed(self, event: Input.Changed) -> None:
        self.update_options(event.value)

    def update_options(self, search_term: str) -> None:
        option_list = self.query_one(OptionList)
        option_list.clear_options()
        term = search_term.lower()
        for i, (p_name, j_name) in enumerate(self.jobs):
            label = f"{j_name} ({p_name})"
            if term in label.lower():
                option_list.add_option(Option(prompt=label, id=str(i)))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id is not None:
            idx = int(event.option_id)
            selected_project, selected_job = self.jobs[idx]
            self.dismiss((selected_project, selected_job))

    def action_cancel(self) -> None:
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
        yield Container(
            Label("Are you sure you want to delete this log?", id="question"),
            Button("Yes (y)", variant="error", id="yes"),
            Button("No (n)", variant="primary", id="no"),
            id="confirm-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
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
        self.edit_mode = "memo"  # "memo" or "date"

    def action_cancel(self) -> None:
        self.can_focus = False
        self.styles.display = "none"
        self.app.query_one(DataTable).focus()

    def action_increment(self) -> None:
        self._adjust_value(1)

    def action_decrement(self) -> None:
        self._adjust_value(-1)

    def _adjust_value(self, delta: int) -> None:
        if self.edit_mode != "date":
            return

        cursor_pos = self.cursor_position
        val = self.value

        try:
            is_full = True
            try:
                dt = datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                dt = datetime.strptime(val, "%Y-%m-%d")
                is_full = False

            if cursor_pos <= 4:
                dt = dt.replace(year=dt.year + delta)
            elif cursor_pos <= 7:
                month = dt.month + delta
                year = dt.year
                if month > 12:
                    month -= 12
                    year += 1
                elif month < 1:
                    month += 12
                    year -= 1
                if month < 12:
                    next_month = datetime(year, month % 12 + 1, 1)
                    last_day_of_month = (next_month - timedelta(days=1)).day
                else:
                    last_day_of_month = 31
                day = min(dt.day, last_day_of_month)
                dt = dt.replace(year=year, month=month, day=day)
            elif cursor_pos <= 10:
                dt += timedelta(days=delta)
            elif cursor_pos <= 13 and is_full:
                dt += timedelta(hours=delta)
            elif cursor_pos <= 16 and is_full:
                dt += timedelta(minutes=delta)
            elif is_full:
                dt += timedelta(seconds=delta)

            self.value = (
                dt.strftime("%Y-%m-%d %H:%M:%S") if is_full else dt.strftime("%Y-%m-%d")
            )
            self.cursor_position = cursor_pos
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
                "\nSidebar Focus (Projects & Jobs):\n"
                "  enter   : Start selected job\n"
                "\nMain List Focus (Logs):\n"
                "  enter   : Edit selected cell\n"
                "  shift+d : Delete selected log\n"
                "\nEdit Mode:\n"
                "  enter   : Save changes\n"
                "  esc     : Cancel edit\n"
                "  up/down : Adjust values for date/time fields"
            )

    def on_key(self, event) -> None:
        """Dismiss the modal on any key press."""
        self.dismiss()


class ExportLogsModal(ModalScreen[tuple[str, str]]):
    """Modal to enter file paths for exporting logs."""

    CSS = """
    ExportLogsModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #export-dialog {
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 1fr 1fr;
        padding: 1 2;
        width: 60;
        height: 18;
        border: thick $background 80%;
        background: $surface;
    }
    .export-label {
        column-span: 2;
        height: 1fr;
        content-align: left bottom;
    }
    #export-profile, #export-output {
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
        yield Container(
            Label("Profile (.toml):", classes="export-label"),
            Input(value=str(db.DB_DIR / "profile.toml"), id="export-profile"),
            Label("Output CSV Path:", classes="export-label"),
            Input(value="report.csv", id="export-output"),
            Button("Export", variant="success", id="btn-export", classes="dialog-buttons"),
            Button("Cancel", variant="error", id="btn-cancel", classes="dialog-buttons"),
            id="export-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-export":
            profile = self.query_one("#export-profile", Input).value.strip()
            output = self.query_one("#export-output", Input).value.strip()
            if profile and output:
                self.dismiss((profile, output))
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
