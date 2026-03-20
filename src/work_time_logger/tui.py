"""Textual user interface for Work Time Logger."""

import traceback
from datetime import datetime
from functools import partial

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Tree,
)

from . import operations
from .widgets import ConfirmDeleteModal, HelpModal, JobSelectionModal, OverlayInput


class ProjectsTree(Tree):
    """A custom Tree widget for displaying projects and their children jobs.

    This widget handles selecting jobs to start tracking and provides
    a shortcut to add manual log entries.

    Attributes:
        BINDINGS (list[Binding]): Keyboard shortcuts for this widget.
    """

    BINDINGS = [
        Binding("enter", "select_cursor", "Start Job", show=True),
        Binding("a", "add_job_log", "Add Log", show=True),
    ]

    def action_add_job_log(self) -> None:
        """Adds a new log assigned to the currently selected job without starting a timer.

        This action is triggered by the 'a' key binding. It calls
        `operations.create_assigned_log` and refreshes the application data.
        """
        node = self.cursor_node
        if node and not node.allow_expand:
            job_name = str(node.label)
            project_name = str(node.parent.label)
            try:
                operations.create_assigned_log(project_name, job_name)
                self.app.refresh_data()
            except Exception as e:
                self.app.notify(f"Error: {e}", severity="error")


class LogsTable(DataTable):
    """A custom DataTable widget for displaying time log entries.

    Provides bindings for editing and deleting logs directly from the table.

    Attributes:
        BINDINGS (list[Binding]): Keyboard shortcuts for this widget.
    """

    BINDINGS = [
        Binding("enter", "select_cursor", "Edit", show=True),
        Binding("D", "app.delete_log", "Delete", show=True),
    ]


class WtlApp(App):
    """The main Textual application for Work Time Logger.

    This app provides a two-pane interface: a projects/jobs tree on the left
    and a records table on the right. It supports filtering, dashboard views,
    and log exporting.

    Attributes:
        CSS (str): The CSS styles for the application.
        BINDINGS (list[Binding]): Global keyboard shortcuts for the application.
    """

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
        Binding("tab", "switch_focus", "Focus", show=True),
        Binding("s", "start_job", "Start", show=True),
        Binding("x", "stop_job", "Stop", show=True),
        Binding("f", "show_filter", "Filter", show=True),
        Binding("d", "show_dashboard", "Dashboard", show=True),
        Binding("v", "show_summary", "Daily Summary", show=True),
        Binding("e", "export_logs", "Export Logs", show=True),
        Binding("h", "show_help", "Help", show=True),
        # 隠しコマンド
        Binding("q", "quit", "Quit", show=False),
        Binding("f1", "show_help", "Help", show=False),
        Binding("S", "start_unassigned", "Start Unassigned Timer", show=False),
        Binding("A", "add_empty_log", "Add Empty Log", show=False),
    ]

    def __init__(self, **kwargs):
        """Initializes the Work Time Logger application.

        Args:
            **kwargs: Standard Textual App keyword arguments.
        """
        super().__init__(**kwargs)
        self.filter_project = None
        self.filter_job = None
        self.filter_date_start = None
        self.filter_date_end = None

        # Load duration step from profile
        self.duration_step = 0.1
        try:
            profile_path = operations.db.DB_DIR / "profile.toml"
            if profile_path.exists():
                import tomllib

                with open(profile_path, "rb") as f:
                    config = tomllib.load(f)
                    self.duration_step = config.get("tui", {}).get("duration_step", 0.1)
        except (OSError, tomllib.TOMLDecodeError):
            # Profile is optional; if missing or broken, TUI will use defaults.
            pass

    def compose(self) -> ComposeResult:
        """Composes the child widgets for the application.

        This Textual lifecycle method is called to build the application's UI.

        Returns:
            ComposeResult: The standard Textual compose result, yielding widgets.
        """
        yield Header()
        with Horizontal():
            with Vertical(id="sidebar"):
                self.projects_tree = ProjectsTree("Projects & Jobs")
                self.projects_tree.root.expand()
                yield self.projects_tree
            with Vertical(id="main-content"):
                self.logs_table = LogsTable(cursor_type="cell")
                self.logs_table.add_columns(
                    "ID",
                    "Project",
                    "Job",
                    "Date",
                    "Start Time",
                    "End Time",
                    "Duration (h)",
                    "Memo",
                )
                yield self.logs_table
        yield Footer()
        yield OverlayInput(id="edit-overlay")

    def on_mount(self) -> None:
        """Called when the application is mounted.

        This Textual lifecycle method is invoked after the DOM is ready.
        It refreshes data, configures the overlay input, and sets initial focus.
        """
        self.refresh_data()
        overlay = self.query_one("#edit-overlay", OverlayInput)
        overlay.can_focus = False
        overlay.duration_step = self.duration_step
        self.logs_table.focus()

    def refresh_data(self) -> None:
        """Refreshes all data displayed in the application.

        This method reloads projects, jobs, and log entries, applying any active filters.
        It also attempts to preserve the cursor position and scroll offset in the logs table.
        """
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

        # Apply current filters
        all_logs = operations.list_logs()
        filtered = []
        for log in all_logs:
            if self.filter_project and log["project_name"] != self.filter_project:
                continue
            if self.filter_job and log["job_name"] != self.filter_job:
                continue
            log_date = log["start_time"][:10]
            if self.filter_date_start and log_date < self.filter_date_start:
                continue
            if self.filter_date_end and log_date > self.filter_date_end:
                continue
            filtered.append(log)
        self.logs = filtered
        for log_entry in self.logs:
            p_name = log_entry["project_name"] or "[未割り当て]"
            j_name = log_entry["job_name"] or "[未割り当て]"

            start_iso = log_entry["start_time"]
            end_iso = log_entry["end_time"]

            log_date = start_iso[:10]

            def format_rel(iso_str, log_date=log_date):
                if not iso_str:
                    return "Running..."
                dt = datetime.fromisoformat(iso_str)
                base = datetime.fromisoformat(log_date + "T00:00:00")
                diff = dt - base
                secs = int(diff.total_seconds())
                return f"{secs // 3600:02}:{(secs % 3600) // 60:02}"

            start_disp = format_rel(start_iso)
            end_disp = format_rel(end_iso)
            memo = log_entry["memo"] or ""
            duration_hours = log_entry["duration_hours"]

            if duration_hours is not None:
                # duration_hours manually set: strike and dim start/end
                dim_start = f"[strike][#585858]{start_disp}[/#585858][/strike]"
                dim_end = f"[strike][#585858]{end_disp}[/#585858][/strike]"
                dur_str = str(duration_hours)
            else:
                dim_start = start_disp
                dim_end = end_disp
                try:
                    if start_iso and end_iso:
                        s = datetime.fromisoformat(start_iso)
                        e = datetime.fromisoformat(end_iso)
                        calc = round((e - s).total_seconds() / 3600, 2)
                        dur_str = f"[#79a8a8]{calc}[/#79a8a8]"
                    else:
                        dur_str = ""
                except (ValueError, TypeError):
                    # In case of malformed ISO strings or other calculation errors,
                    # we display an empty string rather than crashing the TUI.
                    dur_str = ""

            self.logs_table.add_row(
                str(log_entry["id"]),
                p_name,
                j_name,
                log_date,
                dim_start,
                dim_end,
                dur_str,
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
        """Handles the `Tree.NodeSelected` event when a node in the ProjectsTree is selected.

        If a leaf node (job) is selected, it attempts to start a timer for that job.
        This event is typically triggered by pressing Enter on a tree node.

        Args:
            event (Tree.NodeSelected): The event object containing information about the selected node.
        """
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
        """Commits updates to a log entry in the database.

        Args:
            log_entry (dict): The original log entry dictionary.
            **kwargs: Keyword arguments for the fields to update (e.g., `project_name`, `memo`).
        """
        data = {
            "log_id": log_entry["id"],
            "project_name": log_entry["project_name"],
            "job_name": log_entry["job_name"],
            "start_time": log_entry["start_time"],
            "end_time": log_entry["end_time"],
            "memo": log_entry["memo"],
            "duration_hours": log_entry["duration_hours"],
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
        """Updates the project and job for a given log entry.

        Args:
            log_entry (dict): The log entry to update.
            result (tuple[str, str] | None): A tuple containing (project_name, job_name)
                or None if no selection was made.
        """
        if result is None:
            return
        p_name, j_name = result
        self._commit_log_update(log_entry, project_name=p_name, job_name=j_name)

    def _update_start_time(self, log_entry: dict, result: str | None) -> None:
        """Updates the start time for a given log entry.

        Args:
            log_entry (dict): The log entry to update.
            result (str | None): The new start time string (ISO format) or None.
        """
        if result is None:
            return
        self._commit_log_update(log_entry, start_time=result)

    def _update_end_time(self, log_entry: dict, result: str | None) -> None:
        """Updates the end time for a given log entry.

        Args:
            log_entry (dict): The log entry to update.
            result (str | None): The new end time string (ISO format) or None.
        """
        if result is None:
            return
        self._commit_log_update(log_entry, end_time=result)

    def _update_memo(self, log_entry: dict, result: str | None) -> None:
        """Updates the memo for a given log entry.

        Args:
            log_entry (dict): The log entry to update.
            result (str | None): The new memo string or None.
        """
        if result is None:
            return
        self._commit_log_update(log_entry, memo=result)

    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        """Handles the `DataTable.CellSelected` event when a cell in the LogsTable is selected.

        This event is typically triggered by pressing Enter on a table cell.
        It determines the column and shows an appropriate editor (modal or overlay input).

        Args:
            event (DataTable.CellSelected): The event object containing information about the selected cell.
        """
        if not event.cell_key.row_key.value:
            return
        log_id = int(event.cell_key.row_key.value)
        log_entry = next((entry for entry in self.logs if entry["id"] == log_id), None)
        if not log_entry:
            return

        col_index = event.coordinate.column

        # Columns: 0:ID, 1:Project, 2:Job, 3:Date, 4:Start Time, 5:End Time, 6:Duration (h), 7:Memo
        if col_index in (1, 2):
            callback = partial(self._update_job_for_log, log_entry)
            self.push_screen(JobSelectionModal(), callback)
        elif col_index == 3:
            # Date field
            value = log_entry["start_time"][:10] if log_entry["start_time"] else ""
            self.show_edit_overlay(log_entry, 3, value, "date_only", event.coordinate)
        elif col_index == 4:
            # Start Time field
            raw = log_entry["start_time"]
            if raw and len(raw) >= 19:
                value = raw[11:16]  # HH:mm
            else:
                value = raw or ""
            self.show_edit_overlay(log_entry, 4, value, "time_only", event.coordinate)
        elif col_index == 5:
            # End Time field
            raw = log_entry["end_time"]
            if raw and len(raw) >= 19:
                value = raw[11:16]  # HH:mm
            else:
                value = raw or ""
            self.show_edit_overlay(log_entry, 5, value, "time_only", event.coordinate)
        elif col_index == 6:
            # Duration field
            value = (
                str(log_entry["duration_hours"])
                if log_entry["duration_hours"] is not None
                else ""
            )
            self.show_edit_overlay(log_entry, 6, value, "duration", event.coordinate)
        elif col_index == 7:
            # Memo field
            value = log_entry["memo"] or ""
            self.show_edit_overlay(log_entry, 7, value, "memo", event.coordinate)

    def show_edit_overlay(
        self, log_entry: dict, col_index: int, value: str, edit_mode: str, coordinate
    ) -> None:
        """Displays the `OverlayInput` widget for editing a specific cell.

        Args:
            log_entry (dict): The log entry being edited.
            col_index (int): The column index of the cell being edited.
            value (str): The current value of the cell.
            edit_mode (str): The editing mode for the overlay input (e.g., "date_only", "time_only", "memo").
            coordinate (Coordinate): The `DataTable` coordinate of the cell.
        """
        self._editing_log_entry = log_entry
        self._editing_col_index = col_index

        inp = self.query_one("#edit-overlay", OverlayInput)
        inp.edit_mode = edit_mode
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
        """Handles the `Input.Submitted` event from the edit overlay.

        This event is triggered when the user submits input in the `OverlayInput` widget.
        It validates the input based on the `edit_mode` and updates the corresponding
        log entry field.

        Args:
            event (Input.Submitted): The event object from the submitted input.
        """
        val = event.value.strip()
        inp = event.control
        if inp.edit_mode == "date_only":
            try:
                # Ensure it's valid date
                datetime.strptime(val, "%Y-%m-%d")
            except ValueError:
                self.notify("Format must be YYYY-MM-DD", severity="error")
                return
        elif inp.edit_mode == "time_only":
            # HH:mm or full ISO
            try:
                if " " in val:
                    val = val.replace(" ", "T")
                if len(val) == 5 and ":" in val:  # HH:mm
                    # Check if valid time
                    try:
                        h, m = map(int, val.split(":"))
                        if not (0 <= h < 24 and 0 <= m < 60):
                            raise ValueError("Invalid time values.")
                    except ValueError:
                        raise ValueError("Format must be HH:mm (e.g. 09:30)") from None
                else:
                    # Try full iso parse
                    datetime.fromisoformat(val)
            except ValueError as e:
                self.notify(f"Invalid time: {e}", severity="error")
                return

            # Cross-validation: start <= end
            current_log = self._editing_log_entry
            new_val = val
            if len(val) == 5:
                # Need date to compare
                dt_part = (current_log["end_time"] or current_log["start_time"])[:10]
                new_val = f"{dt_part}T{val}:00"

            try:
                if self._editing_col_index == 4:  # Start Time
                    st = datetime.fromisoformat(new_val)
                    if current_log["end_time"]:
                        et = datetime.fromisoformat(current_log["end_time"])
                        if et < st:
                            self.notify(
                                "Start time cannot be after end time.", severity="error"
                            )
                            return
                elif self._editing_col_index == 5:  # End Time
                    et = datetime.fromisoformat(new_val)
                    st = datetime.fromisoformat(current_log["start_time"])
                    if et < st:
                        self.notify(
                            "End time cannot be before start time.", severity="error"
                        )
                        return
            except (ValueError, TypeError):
                # Invalid date formats or mixed types; validation handled by callers.
                pass

        # Columns: 0:ID, 1:Project, 2:Job, 3:Date, 4:Start Time, 5:End Time, 6:Duration (h), 7:Memo
        if self._editing_col_index == 3:
            # Update date of start_time
            if len(val) == 10:
                current_start = self._editing_log_entry["start_time"]
                new_start = val + current_start[10:]
                self._update_start_time(self._editing_log_entry, new_start)
        elif self._editing_col_index == 4:
            # Start Time
            if len(val) == 5 and ":" in val:  # HH:mm
                current_date = self._editing_log_entry["start_time"][:10]
                val = f"{current_date}T{val}:00"
            self._update_start_time(self._editing_log_entry, val)
        elif self._editing_col_index == 5:
            # End Time
            if len(val) == 5 and ":" in val:  # HH:mm
                current_date = (
                    self._editing_log_entry["end_time"]
                    or self._editing_log_entry["start_time"]
                )[:10]
                val = f"{current_date}T{val}:00"
            self._update_end_time(self._editing_log_entry, val)
        elif self._editing_col_index == 6:
            # duration_hours
            try:
                duration = float(val) if val else None
            except ValueError:
                self.notify("数値を入力してください (例: 2.5)", severity="error")
                return
            self._commit_log_update(self._editing_log_entry, duration_hours=duration)
        elif self._editing_col_index == 7:
            # Memo
            self._update_memo(self._editing_log_entry, val)

        inp.can_focus = False
        inp.styles.display = "none"
        self.logs_table.focus()

    def action_show_help(self) -> None:
        """Action to display the help modal.

        This action is triggered by the 'h' or 'f1' key binding.
        """
        self.push_screen(HelpModal())

    def action_switch_focus(self) -> None:
        """Action to switch focus between the ProjectsTree and LogsTable.

        This action is triggered by the 'tab' key binding.
        """
        if self.focused == self.projects_tree:
            self.logs_table.focus()
        else:
            self.projects_tree.focus()

    def action_start_job(self) -> None:
        """Action to start a job timer.

        If a job is selected in the ProjectsTree, it starts that job.
        Otherwise, it opens a `JobSelectionModal` to choose a job.
        This action is triggered by the 's' key binding.
        """
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
            """Helper function to check for running jobs before showing the selection modal."""
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
        """Starts a timer for the selected project and job.

        Args:
            selection (tuple[str, str] | None): A tuple containing (project_name, job_name)
                or None if no selection was made.
        """
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

        def handle_export(data: tuple[str, str, str] | None) -> None:
            if not data:
                return
            profile_path, output_path, date_val = data
            target_date = None if date_val.lower() == "all" else date_val
            try:
                count = exporter.export_logs(
                    profile_path, output_path, target_date=target_date
                )
                if count > 0:
                    label = target_date if target_date else "all dates"
                    self.notify(
                        f"Successfully exported {count} grouped rows to {output_path} ({label})"
                    )
                else:
                    self.notify("No logs matched or exported.", severity="warning")
            except Exception as e:
                with open("wtl_error.log", "a") as f:
                    f.write(f"Export Error: {e}\n")
                    traceback.print_exc(file=f)
                self.notify(f"Export Error: {e} (See wtl_error.log)", severity="error")

        self.push_screen(ExportLogsModal(), handle_export)

    def action_show_summary(self) -> None:
        """Action handler to show the Daily Summary modal."""
        from .widgets import DailySummaryModal

        self.push_screen(DailySummaryModal())

    def action_show_dashboard(self) -> None:
        """Action handler to show the Dashboard screen."""
        from .dashboard import DashboardScreen

        self.push_screen(DashboardScreen())

    def action_show_filter(self) -> None:
        """Action handler to show the Filter modal."""
        from .widgets import FilterModal

        current = {
            "project": self.filter_project,
            "job": self.filter_job,
            "start": self.filter_date_start,
            "end": self.filter_date_end,
        }

        def handle_filter(res: dict | None) -> None:
            if res is None:
                return
            self.filter_project = res["project"]
            self.filter_job = res["job"]
            self.filter_date_start = res["start"]
            self.filter_date_end = res["end"]
            self.refresh_data()
            if any(res.values()):
                self.notify("Filters applied.")
            else:
                self.notify("Filters cleared.")

        self.push_screen(FilterModal(current), handle_filter)


if __name__ == "__main__":
    app = WtlApp()
    app.run()
