"""Textual user interface for Work Time Logger."""

import traceback
from datetime import datetime
from functools import partial

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Tree,
)
from textual.binding import Binding

from . import operations
from .widgets import ConfirmDeleteModal, HelpModal, JobSelectionModal, OverlayInput

class ProjectsTree(Tree):
    BINDINGS = [
        Binding("enter", "select_cursor", "Start Job", show=True),
    ]

class LogsTable(DataTable):
    BINDINGS = [
        Binding("enter", "select_cursor", "Edit", show=True),
        Binding("D", "app.delete_log", "Delete", show=True),
    ]


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
    #edit-overlay {
        display: none;
        layer: overlay;
        padding: 0 1;
        border: none;
    }
    """

    BINDINGS = [
        Binding("h", "show_help", "Help", show=True),
        Binding("f1", "show_help", "Help", show=False),
        Binding("tab", "switch_focus", "Focus", show=True),
        Binding("x", "stop_job", "Stop", show=True),
        Binding("q", "quit", "Quit", show=False),
        Binding("s", "start_job", "Search Job", show=False),
        Binding("S", "start_unassigned", "Start Unassigned Timer", show=False),
        Binding("A", "add_empty_log", "Add Empty Log", show=False),
        Binding("e", "export_logs", "Export Logs", show=True),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        with Horizontal():
            with Vertical(id="sidebar"):
                self.projects_tree = ProjectsTree("Projects & Jobs")
                self.projects_tree.root.expand()
                yield self.projects_tree
            with Vertical(id="main-content"):
                self.logs_table = LogsTable(cursor_type="cell")
                self.logs_table.add_columns(
                    "ID", "Project", "Job", "Start Time", "End Time", "Memo"
                )
                yield self.logs_table
        yield Footer()
        yield OverlayInput(id="edit-overlay")

    def on_mount(self) -> None:
        """Called when app starts."""
        self.refresh_data()
        self.query_one("#edit-overlay").can_focus = False
        self.logs_table.focus()

    def refresh_data(self) -> None:
        try:
            cursor_coord = self.logs_table.cursor_coordinate
            scroll_x, scroll_y = self.logs_table.scroll_offset
        except (AttributeError, ValueError):
            # If the table is not yet fully initialized or populated,
            # these lookups might fail. We default to (0,0) in such cases.
            cursor_coord = None
            scroll_x, scroll_y = 0, 0

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

        if cursor_coord:
            try:
                self.logs_table.move_cursor(
                    row=cursor_coord.row,
                    column=cursor_coord.column,
                    animate=False,
                )
            except (ValueError, IndexError):
                # Table content might have changed (e.g. log deleted)
                # making the coordinate invalid.
                pass
        try:
            self.logs_table.scroll_to(x=scroll_x, y=scroll_y, animate=False)
        except (ValueError, IndexError):
            # Scroll target might no longer be reachable.
            pass

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
            value = log_entry["start_time"] or ""
            self.show_edit_overlay(log_entry, 3, value, "date", event.coordinate)
        elif col_index == 4:
            value = log_entry["end_time"] or ""
            self.show_edit_overlay(log_entry, 4, value, "date", event.coordinate)
        elif col_index == 5:
            value = log_entry["memo"] or ""
            self.show_edit_overlay(log_entry, 5, value, "memo", event.coordinate)

    def show_edit_overlay(
        self, log_entry: dict, col_index: int, value: str, edit_mode: str, coordinate
    ) -> None:
        self._editing_log_entry = log_entry
        self._editing_col_index = col_index

        inp = self.query_one("#edit-overlay", OverlayInput)
        inp.edit_mode = edit_mode
        if edit_mode == "date" and len(value) >= 19:
            inp.edit_mode = (
                "date"  # Maybe it should be datetime? Oh, TimeEditModal extracted it.
            )
            # wait, timeEdit modal was used for BOTH. I will just render full datetime
            pass

        # Format the value for editing
        if edit_mode == "date" and "T" in value:
            inp.value = value.replace("T", " ")
        else:
            inp.value = value

        region = self.logs_table._get_cell_region(coordinate)
        table_x, table_y = self.logs_table.region.x, self.logs_table.region.y
        scroll_x, scroll_y = self.logs_table.scroll_offset

        abs_x = table_x + region.x - scroll_x
        abs_y = table_y + region.y - scroll_y

        inp.styles.offset = (abs_x, abs_y)
        inp.styles.width = region.width
        inp.styles.height = region.height
        inp.styles.display = "block"
        inp.can_focus = True
        self.set_timer(0.01, inp.focus)

    @on(Input.Submitted, "#edit-overlay")
    def on_edit_overlay_submitted(self, event: Input.Submitted) -> None:
        val = event.value.strip()
        inp = event.control
        if inp.edit_mode == "date":
            val = val.replace("/", "-")
            try:
                if len(val) > 10:
                    dt = datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
                    val = dt.strftime("%Y-%m-%dT%H:%M:%S")
                else:
                    dt = datetime.strptime(val, "%Y-%m-%d")
                    val = dt.strftime("%Y-%m-%dT00:00:00")
            except ValueError:
                self.notify("Format must be YYYY-MM-DD HH:MM:SS", severity="error")
                return

        if self._editing_col_index == 3:
            self._update_start_time(self._editing_log_entry, val)
        elif self._editing_col_index == 4:
            self._update_end_time(self._editing_log_entry, val)
        elif self._editing_col_index == 5:
            self._update_memo(self._editing_log_entry, val)

        inp.can_focus = False
        inp.styles.display = "none"
        self.logs_table.focus()

    def action_show_help(self) -> None:
        self.push_screen(HelpModal())

    def action_switch_focus(self) -> None:
        if self.focused == self.projects_tree:
            self.logs_table.focus()
        else:
            self.projects_tree.focus()

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
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    def action_stop_job(self) -> None:
        try:
            operations.stop_log()
            self.refresh_data()
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    def action_start_unassigned(self) -> None:
        try:
            operations.start_log(None, None)
            self.refresh_data()
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    def action_add_empty_log(self) -> None:
        """Action handler to add a new empty log."""
        try:
            operations.create_empty_log()
            self.refresh_data()
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    def action_delete_log(self) -> None:
        """Action handler to delete the currently selected log."""
        if self.focused != self.logs_table:
            return
        coord = self.logs_table.cursor_coordinate
        if not coord:
            return
        try:
            cell_key = self.logs_table.coordinate_to_cell_key(coord)
        except (ValueError, KeyError, IndexError):
            # The coordinate might be obsolete or invalid at this point.
            return
        if not cell_key or not cell_key.row_key or not cell_key.row_key.value:
            return

        def check_delete(confirm: bool) -> None:
            if confirm:
                try:
                    log_id = int(cell_key.row_key.value)
                    operations.delete_log(log_id)
                    self.refresh_data()
                except Exception as e:
                    self.notify(f"Error: {e}", severity="error")

        self.push_screen(ConfirmDeleteModal(), check_delete)

    def action_export_logs(self) -> None:
        """Action handler to export logs using a user-specified TOML profile."""
        from .widgets import ExportLogsModal
        from . import exporter
        
        def handle_export(data: tuple[str, str] | None) -> None:
            if not data:
                return
            profile_path, output_path = data
            try:
                count = exporter.export_logs(profile_path, output_path)
                if count > 0:
                    self.notify(f"Successfully exported {count} grouped rows to {output_path}")
                else:
                    self.notify("No logs matched or exported.", severity="warning")
            except Exception as e:
                with open("wtl_error.log", "a") as f:
                    f.write(f"Export Error: {e}\n")
                    traceback.print_exc(file=f)
                self.notify(f"Export Error: {e} (See wtl_error.log)", severity="error")

        self.push_screen(ExportLogsModal(), handle_export)
if __name__ == "__main__":
    app = WtlApp()
    app.run()
