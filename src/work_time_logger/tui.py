"""Textual user interface for Work Time Logger."""

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


class LogEditModal(ModalScreen[dict]):
    """Modal to edit a log entry."""

    CSS = """
    LogEditModal {
        align: center middle;
    }
    #edit-dialog {
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

    def __init__(self, log_data: dict):
        super().__init__()
        self.log_data = log_data

    def compose(self) -> ComposeResult:
        with Container(id="edit-dialog"):
            yield Label(
                f"Editing Log ID: {self.log_data['id']}", classes="input-container"
            )
            yield Input(
                value=self.log_data.get("project_name") or "",
                placeholder="Project Name",
                id="p_name",
                classes="input-container",
            )
            yield Input(
                value=self.log_data.get("job_name") or "",
                placeholder="Job Name",
                id="j_name",
                classes="input-container",
            )
            yield Input(
                value=self.log_data.get("start_time") or "",
                placeholder="Start Time (ISO)",
                id="start_time",
                classes="input-container",
            )
            yield Input(
                value=self.log_data.get("end_time") or "",
                placeholder="End Time (ISO)",
                id="end_time",
                classes="input-container",
            )
            yield Input(
                value=self.log_data.get("memo") or "",
                placeholder="Memo",
                id="memo",
                classes="input-container",
            )
            with Horizontal(id="buttons"):
                yield Button("Save", id="save", variant="success")
                yield Button("Cancel", id="cancel", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            p_name = self.query_one("#p_name", Input).value.strip()
            j_name = self.query_one("#j_name", Input).value.strip()
            start = self.query_one("#start_time", Input).value.strip()
            end = self.query_one("#end_time", Input).value.strip()
            memo = self.query_one("#memo", Input).value.strip()
            self.dismiss(
                {
                    "id": self.log_data["id"],
                    "project_name": p_name if p_name else None,
                    "job_name": j_name if j_name else None,
                    "start_time": start,
                    "end_time": end if end else None,
                    "memo": memo,
                }
            )
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
                self.logs_table = DataTable(cursor_type="row")
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

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle Enter key on the Logs Table to edit a log."""
        if not event.row_key.value:
            return
        log_id = int(event.row_key.value)
        log_entry = next((entry for entry in self.logs if entry["id"] == log_id), None)
        if log_entry:
            self.push_screen(LogEditModal(dict(log_entry)), self.update_log_from_modal)

    def update_log_from_modal(self, result: dict | None) -> None:
        """Callback to handle the result of the LogEditModal."""
        if result is None:
            return
        try:
            operations.update_log(
                log_id=result["id"],
                project_name=result["project_name"],
                job_name=result["job_name"],
                start_time=result["start_time"],
                end_time=result["end_time"],
                memo=result["memo"],
            )
            self.refresh_data()
            self.notify("Log updated successfully!", variant="success")
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

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
