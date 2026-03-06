"""Textual user interface for Work Time Logger."""

import traceback
from functools import partial

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    OptionList,
    Tree,
)
from textual.widgets.option_list import Option

from . import operations


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


class TimeEditModal(ModalScreen[str | None]):
    """Modal to edit a time (YYYY-MM-DD and HH:MM:SS format)."""

    CSS = """
    TimeEditModal {
        align: center middle;
    }
    #time-dialog {
        width: 40;
        height: auto;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }
    .input-container {
        margin-bottom: 1;
    }
    #buttons {
        height: auto;
        align: right middle;
    }
    Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, title: str, initial_value: str | None):
        super().__init__()
        self.dialog_title = title
        self.initial_date = ""
        self.initial_time = ""
        if initial_value and len(initial_value) >= 19:
            self.initial_date = initial_value[:10]
            self.initial_time = initial_value[11:19]
        elif initial_value:
            self.initial_date = initial_value

    def compose(self) -> ComposeResult:
        with Container(id="time-dialog"):
            yield Label(self.dialog_title, classes="input-container")
            yield Input(
                value=self.initial_date,
                placeholder="YYYY-MM-DD",
                id="date_input",
                classes="input-container",
            )
            yield Input(
                value=self.initial_time,
                placeholder="HH:MM:SS",
                id="time_input",
                classes="input-container",
            )
            with Horizontal(id="buttons"):
                yield Button("Save", id="save", variant="success")
                yield Button("Cancel", id="cancel", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            date_val = self.query_one("#date_input", Input).value.strip()
            time_val = self.query_one("#time_input", Input).value.strip()
            if not date_val and not time_val:
                self.dismiss(None)
            else:
                self.dismiss(f"{date_val}T{time_val}")
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class MemoEditModal(ModalScreen[str | None]):
    """Modal to edit a memo."""

    CSS = """
    MemoEditModal {
        align: center middle;
    }
    #memo-dialog {
        width: 60;
        height: auto;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }
    .input-container {
        margin-bottom: 1;
    }
    #buttons {
        height: auto;
        align: right middle;
    }
    Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, title: str, initial_value: str | None):
        super().__init__()
        self.dialog_title = title
        self.initial_value = initial_value or ""

    def compose(self) -> ComposeResult:
        with Container(id="memo-dialog"):
            yield Label(self.dialog_title, classes="input-container")
            yield Input(
                value=self.initial_value,
                placeholder="Memo contents...",
                id="memo_input",
                classes="input-container",
            )
            with Horizontal(id="buttons"):
                yield Button("Save", id="save", variant="success")
                yield Button("Cancel", id="cancel", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            memo_val = self.query_one("#memo_input", Input).value.strip()
            self.dismiss(memo_val)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class WtlApp(App):
    """A Textual TUI for Work Time Logger."""

    CSS = """
    #sidebar {
        width: 30%;
        height: 100%;
        border-right: solid green;
    }
    #main-content {
        width: 70%;
        height: 100%;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("s", "start_job", "Start/Search Job"),
        ("S", "start_unassigned", "Start Unassigned Timer"),
        ("A", "add_empty_log", "Add Empty Log"),
        ("x", "stop_job", "Stop tracking current Job"),
    ]

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        with Horizontal():
            with Vertical(id="sidebar"):
                self.projects_tree = Tree("Projects & Jobs")
                self.projects_tree.root.expand()
                yield self.projects_tree
            with Vertical(id="main-content"):
                self.logs_table = DataTable(cursor_type="cell")
                self.logs_table.add_columns(
                    "ID", "Project", "Job", "Start Time", "End Time", "Memo"
                )
                yield self.logs_table
        yield Footer()

    def on_mount(self) -> None:
        """Called when app starts."""
        self.refresh_data()

    def refresh_data(self) -> None:
        # Populate Projects and Jobs tree
        self.projects_tree.clear()
        projects = operations.list_projects()
        for p in projects:
            p_node = self.projects_tree.root.add(p["name"], expand=True)
            jobs = operations.list_jobs(p["name"])
            for j in jobs:
                p_node.add_leaf(j["name"])

        # Populate Logs table
        self.logs_table.clear()
        self.logs = operations.list_logs()
        for log_entry in self.logs:
            p_name = log_entry["project_name"] or "[未割り当て]"
            j_name = log_entry["job_name"] or "[未割り当て]"
            end_time = (
                log_entry["end_time"][:19] if log_entry["end_time"] else "Running..."
            )
            memo = log_entry["memo"] or ""
            self.logs_table.add_row(
                str(log_entry["id"]),
                p_name,
                j_name,
                log_entry["start_time"][:19],
                end_time,
                memo,
                key=str(log_entry["id"]),
            )

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle Enter key on the Tree."""
        if not event.node.allow_expand:
            job_name = str(event.node.label)
            project_name = str(event.node.parent.label)

            # To prevent starting if already running
            try:
                operations.start_log("temp_nonexistent", "temp")
            except ValueError as e:
                if "already running" in str(e):
                    self.notify(
                        "A job is already running! Please stop it first.",
                        severity="error",
                    )
                    return
            except Exception:
                pass

            self.start_timer_for_selection((project_name, job_name))

    def _commit_log_update(self, log_entry: dict, **kwargs) -> None:
        data = {
            "log_id": log_entry["id"],
            "project_name": log_entry["project_name"],
            "job_name": log_entry["job_name"],
            "start_time": log_entry["start_time"],
            "end_time": log_entry["end_time"],
            "memo": log_entry["memo"],
        }
        data.update(kwargs)
        try:
            operations.update_log(**data)
            self.refresh_data()
            self.notify("Log updated successfully!", variant="success")
        except Exception as e:
            with open("wtl_error.log", "a") as f:
                f.write("Error in _commit_log_update:\n")
                traceback.print_exc(file=f)
            self.notify(f"Update Error: {e} (See wtl_error.log)", severity="error")

    def _update_job_for_log(
        self, log_entry: dict, result: tuple[str, str] | None
    ) -> None:
        if result is None:
            return
        p_name, j_name = result
        self._commit_log_update(log_entry, project_name=p_name, job_name=j_name)

    def _update_start_time(self, log_entry: dict, result: str | None) -> None:
        if result is None:
            return
        self._commit_log_update(log_entry, start_time=result)

    def _update_end_time(self, log_entry: dict, result: str | None) -> None:
        if result is None:
            return
        self._commit_log_update(log_entry, end_time=result)

    def _update_memo(self, log_entry: dict, result: str | None) -> None:
        if result is None:
            return
        self._commit_log_update(log_entry, memo=result)

    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        """Handle Enter key on a specific cell in the Logs Table."""
        if not event.cell_key.row_key.value:
            return
        log_id = int(event.cell_key.row_key.value)
        log_entry = next((entry for entry in self.logs if entry["id"] == log_id), None)
        if not log_entry:
            return

        col_index = event.coordinate.column

        # Columns mapping: 0:ID, 1:Proj, 2:Job, 3:Start, 4:End, 5:Memo
        if col_index in (1, 2):
            callback = partial(self._update_job_for_log, log_entry)
            self.push_screen(JobSelectionModal(), callback)
        elif col_index == 3:
            callback = partial(self._update_start_time, log_entry)
            self.push_screen(
                TimeEditModal("Edit Start Time", log_entry["start_time"]), callback
            )
        elif col_index == 4:
            callback = partial(self._update_end_time, log_entry)
            self.push_screen(
                TimeEditModal("Edit End Time", log_entry["end_time"]), callback
            )
        elif col_index == 5:
            callback = partial(self._update_memo, log_entry)
            self.push_screen(MemoEditModal("Edit Memo", log_entry["memo"]), callback)

    def action_start_job(self) -> None:
        # If focused on the tree and a leaf node is selected, start that job.
        if (
            self.focused == self.projects_tree
            and self.projects_tree.cursor_node
            and not self.projects_tree.cursor_node.allow_expand
        ):
            job_name = str(self.projects_tree.cursor_node.label)
            project_name = str(self.projects_tree.cursor_node.parent.label)

            try:
                operations.start_log("temp_nonexistent", "temp")
            except ValueError as e:
                if "already running" in str(e):
                    self.notify(
                        "A job is already running! Please stop it first.",
                        severity="error",
                    )
                    return
            except Exception:
                pass

            self.start_timer_for_selection((project_name, job_name))
            return

        def check_running_and_show_modal():
            try:
                # To prevent opening modal if already running
                operations.start_log("temp_nonexistent", "temp")
            except ValueError as e:
                if "already running" in str(e):
                    self.notify(
                        "A job is already running! Please stop it first.",
                        severity="error",
                    )
                    return
            except Exception:
                pass  # Expected since temps fail

            self.push_screen(JobSelectionModal(), self.start_timer_for_selection)

        check_running_and_show_modal()

    def start_timer_for_selection(self, selection: tuple[str, str] | None) -> None:
        if selection is None:
            return

        project_name, job_name = selection
        try:
            operations.start_log(project_name, job_name)
            self.refresh_data()
            self.notify(f"Started tracking: {job_name} ({project_name})")
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    def action_stop_job(self) -> None:
        try:
            operations.stop_log()
            self.refresh_data()
            self.notify("Job stopped tracking!")
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    def action_start_unassigned(self) -> None:
        try:
            operations.start_log(None, None)
            self.refresh_data()
            self.notify("Started tracking an unassigned job!")
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    def action_add_empty_log(self) -> None:
        """Action handler to add a new empty log."""
        try:
            operations.create_empty_log()
            self.refresh_data()
            self.notify("Added an empty log!")
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")


if __name__ == "__main__":
    app = WtlApp()
    app.run()
