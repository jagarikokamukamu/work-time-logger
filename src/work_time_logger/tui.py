"""Textual user interface for Work Time Logger."""

from __future__ import annotations

import tomllib
import traceback
from datetime import date, datetime, timedelta
from enum import IntEnum
from functools import partial
from typing import cast

from rich.text import Text
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

from . import db, operations
from .modals import (
    ConfirmActionModal,
    ConfirmDeleteModal,
    HelpModal,
    JobCodeModal,
    JobSelectionModal,
)
from .widgets import OverlayInput


class LogColumn(IntEnum):
    """Enumeration of columns in the LogsTable."""

    ID = 0
    PROJECT = 1
    JOB = 2
    DATE = 3
    START_TIME = 4
    END_TIME = 5
    DURATION = 6
    MEMO = 7


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
        Binding("c", "show_job_code", "Show Job Code", show=True),
        Binding("z", "toggle_archive", "Archive/Unarchive", show=True),
        Binding("f", "toggle_favorite", "Favorite", show=True),
    ]

    def action_toggle_favorite(self) -> None:
        """Toggles the favorite status of the selected job."""
        node = self.cursor_node
        if node and node.data and node.data["type"] == "job":
            job_name = node.data["job_name"]
            project_name = node.data["project_name"]
            try:
                # We need to know current status. Let's find it from list_jobs.
                jobs = operations.list_jobs(project_name, include_archived=True)
                job = next((j for j in jobs if j["name"] == job_name), None)
                if job:
                    new_status = not job["is_favorite"]
                    operations.set_job_favorite(project_name, job_name, new_status)
                    cast("WtlApp", self.app).refresh_data()
            except Exception as e:
                self.app.notify(f"Error: {e}", severity="error")

    def action_toggle_archive(self) -> None:
        """Toggles the archival status of the selected project."""
        node = self.cursor_node
        if node and node.data:
            # If leaf, get parent (project)
            if node.data["type"] == "job":
                node = node.parent

            if not node or not node.data or node.data["type"] != "project":
                return

            project_name = node.data["project_name"]

            try:
                p = operations.get_project(project_name)
                if p:
                    new_status = not p["is_archived"]
                    operations.set_project_archived(project_name, new_status)
                    cast("WtlApp", self.app).refresh_data()
            except Exception as e:
                self.app.notify(f"Error: {e}", severity="error")

    def action_show_job_code(self) -> None:
        """Shows the expansion of the job code for the selected job.

        This action is triggered by the 'c' key binding. It opens a
        `JobCodeModal` with the rendered columns.
        """
        node = self.cursor_node
        if node and node.data and node.data["type"] == "job":
            job_name = node.data["job_name"]
            project_name = node.data["project_name"]
            self.app.push_screen(JobCodeModal(project_name, job_name))

    def action_add_job_log(self) -> None:
        """Adds a new log to the selected job without starting a timer.

        This action is triggered by the 'a' key binding. It calls
        `operations.create_assigned_log` and refreshes the application data.
        """
        node = self.cursor_node
        if node and node.data and node.data["type"] == "job":
            job_name = node.data["job_name"]
            project_name = node.data["project_name"]
            try:
                operations.create_assigned_log(project_name, job_name)
                cast("WtlApp", self.app).refresh_data()
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
        Binding("r", "app.restart_job", "Restart", show=True),
        Binding("p", "app.parallel_clone_assigned", "Parallel Clone (Job)", show=True),
        Binding(
            "P",
            "app.parallel_clone_unassigned",
            "Parallel Clone (Unassigned)",
            show=True,
        ),
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
        Binding("F", "show_filter", "Filter", show=True),
        Binding("d", "show_dashboard", "Dashboard", show=True),
        Binding("v", "show_summary", "Daily Summary", show=True),
        Binding("e", "export_logs", "Export Logs", show=True),
        Binding("h", "show_help", "Help", show=True),
        Binding("ctrl+z", "undo", "Undo", show=True),
        Binding("ctrl+y", "redo", "Redo", show=True),
        # Hidden commands
        Binding("q", "quit", "Quit", show=False),
        Binding("f1", "show_help", "Help", show=False),
        Binding("S", "start_unassigned", "Start Unassigned Timer", show=False),
        Binding("A", "add_empty_log", "Add Empty Log", show=False),
        Binding("Z", "toggle_show_archived", "Toggle Archived", show=True),
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
        self.show_archived = False
        self.favorite_mark = "🌟"
        self.favorite_style = ""
        self.duration_step = 0.1
        self.copy_memo_on_restart = True

        try:
            profile_path = db.DB_DIR / "profile.toml"
            if profile_path.exists():
                with open(profile_path, "rb") as f:
                    config = tomllib.load(f)
                    tui_cfg = config.get("tui", {})
                    self.duration_step = tui_cfg.get(
                        "duration_step", self.duration_step
                    )
                    self.copy_memo_on_restart = tui_cfg.get(
                        "copy_memo_on_restart", self.copy_memo_on_restart
                    )
                    self.favorite_mark = tui_cfg.get(
                        "favorite_mark", self.favorite_mark
                    )
                    self.favorite_style = tui_cfg.get(
                        "favorite_style", self.favorite_style
                    )
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
                self.logs_table = LogsTable(cursor_type="cell", id="logs-table")
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

        This method reloads projects, jobs, and log entries, applying any
        active filters. It also attempts to preserve the cursor position
        and scroll offset in the logstable.
        """
        try:
            cursor_coord = self.logs_table.cursor_coordinate
            scroll_x, scroll_y = self.logs_table.scroll_offset
        except (AttributeError, ValueError):
            # If the table is not yet fully initialized or populated,
            # these lookups might fail. We default to (0,0) in such cases.
            cursor_coord = None
            scroll_x, scroll_y = 0, 0

        # Preserve expanded state of project nodes
        # If the tree is empty (initial load), we'll default to expanding everything.
        is_initial_load = not any(self.projects_tree.root.children)
        expanded_projects = {
            node.data["project_name"]
            for node in self.projects_tree.root.children
            if node.is_expanded and node.data and "project_name" in node.data
        }

        # Populate Projects and Jobs tree
        self.projects_tree.clear()
        projects = operations.list_projects(include_archived=self.show_archived)

        # Collect and display Favorites (Pinned)
        favorites = []
        for p in projects:
            p_jobs = operations.list_jobs(p["name"], include_archived=True)
            for j in p_jobs:
                if j["is_favorite"]:
                    favorites.append(j)

        if favorites:
            pinned_node = self.projects_tree.root.add(
                "Pinned", expand=True, data={"type": "pinned_root"}
            )
            for j in favorites:
                # Inside Pinned section, we use a simple label
                # to avoid too much distraction
                label = f"{j['name']} ({j['project_name']})"
                pinned_node.add_leaf(
                    label,
                    data={
                        "type": "job",
                        "job_name": j["name"],
                        "project_name": j["project_name"],
                    },
                )

        for p in projects:
            p_name = p["name"]
            is_archived = p["is_archived"]

            if is_archived:
                label = Text(f"[A] {p_name}", style="italic dim")
            else:
                label = p_name

            should_expand = is_initial_load or (p_name in expanded_projects)

            p_node = self.projects_tree.root.add(
                label,
                expand=should_expand,
                data={
                    "type": "project",
                    "project_name": p_name,
                    "is_archived": is_archived,
                },
            )

            jobs = operations.list_jobs(p_name, include_archived=True)
            for j in jobs:
                j_name = j["name"]
                is_fav = j["is_favorite"]

                j_label = Text(j_name, style="dim") if is_archived else Text(j_name)
                if is_fav:
                    fav_prefix = Text(self.favorite_mark, style=self.favorite_style)
                    fav_prefix.append(" ")
                    j_label = fav_prefix + j_label

                p_node.add_leaf(
                    j_label,
                    data={"type": "job", "job_name": j_name, "project_name": p_name},
                )

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
            p_name = log_entry["project_name"] or "[Unassigned]"
            j_name = log_entry["job_name"] or "[Unassigned]"

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
                dim_start = Text(start_disp, style="strike #585858")
                dim_end = Text(end_disp, style="strike #585858")
                dur_str = Text(str(duration_hours))
            else:
                dim_start = Text(start_disp)
                dim_end = Text(end_disp)
                try:
                    if start_iso and end_iso:
                        s = datetime.fromisoformat(start_iso)
                        e = datetime.fromisoformat(end_iso)
                        calc = round((e - s).total_seconds() / 3600, 2)
                        dur_str = Text(f"{calc}", style="#79a8a8")
                    else:
                        dur_str = Text("")
                except (ValueError, TypeError):
                    # In case of malformed ISO strings or other calculation errors,
                    # we display an empty string rather than crashing the TUI.
                    dur_str = Text("")

            self.logs_table.add_row(
                Text(str(log_entry["id"])),
                Text(str(p_name)),
                Text(str(j_name)),
                Text(str(log_date)),
                dim_start,
                dim_end,
                dur_str,
                Text(str(memo)),
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
        """Handles the `Tree.NodeSelected` event for the ProjectsTree.

        If a leaf node (job) is selected, it attempts to start a timer for that job.
        This event is typically triggered by pressing Enter on a tree node.

        Args:
            event (Tree.NodeSelected): The event object containing information about
                the selected node.
        """
        if event.node.data and event.node.data["type"] == "job":
            job_name = event.node.data["job_name"]
            project_name = event.node.data["project_name"]

            # Use the dedicated check instead of relying on start_log side effects.
            if operations.is_any_job_running():
                self.notify(
                    "A job is already running! Please stop it first.",
                    severity="error",
                )
                return

            self.start_timer_for_selection((project_name, job_name))

    def _commit_log_update(self, log_entry: dict, **kwargs) -> None:
        """Commits updates to a log entry in the database.

        Args:
            log_entry (dict): The original log entry dictionary.
            **kwargs: Keyword arguments for the fields to update
                (e.g., `project_name`, `memo`).
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

    @on(DataTable.CellSelected, "#logs-table")
    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        """Handles the `DataTable.CellSelected` event for the logs table.

        This event is triggered when a cell in the LogsTable is selected,
        typically by pressing Enter. It determines the column and shows an
        appropriate editor (modal or overlay input).

        Args:
            event (DataTable.CellSelected): The event object containing
                information about the selected cell.
        """
        try:
            log_id = int(str(event.cell_key.row_key.value))
        except (ValueError, TypeError):
            return
        log_entry = next((entry for entry in self.logs if entry["id"] == log_id), None)
        if not log_entry:
            return

        col_index = event.coordinate.column

        if col_index in (LogColumn.PROJECT, LogColumn.JOB):
            callback = partial(self._update_job_for_log, log_entry)
            self.push_screen(JobSelectionModal(title="Change Job"), callback)
        elif col_index == LogColumn.DATE:
            # Date field
            value = log_entry["start_time"][:10] if log_entry["start_time"] else ""
            self.show_edit_overlay(
                log_entry, LogColumn.DATE, value, "date_only", event.coordinate
            )
        elif col_index == LogColumn.START_TIME:
            # Start Time field
            raw = log_entry["start_time"]
            if raw and len(raw) >= 19:
                value = raw[11:16]  # HH:mm
            else:
                value = raw or ""
            self.show_edit_overlay(
                log_entry, LogColumn.START_TIME, value, "time_only", event.coordinate
            )
        elif col_index == LogColumn.END_TIME:
            # End Time field
            raw = log_entry["end_time"]
            if raw and len(raw) >= 19:
                value = raw[11:16]  # HH:mm
            else:
                value = raw or ""
            self.show_edit_overlay(
                log_entry, LogColumn.END_TIME, value, "time_only", event.coordinate
            )
        elif col_index == LogColumn.DURATION:
            # Duration field
            value = (
                str(log_entry["duration_hours"])
                if log_entry["duration_hours"] is not None
                else ""
            )
            self.show_edit_overlay(
                log_entry, LogColumn.DURATION, value, "duration", event.coordinate
            )
        elif col_index == LogColumn.MEMO:
            # Memo field
            value = log_entry["memo"] or ""
            self.show_edit_overlay(
                log_entry, LogColumn.MEMO, value, "memo", event.coordinate
            )

    def show_edit_overlay(
        self, log_entry: dict, col_index: int, value: str, edit_mode: str, coordinate
    ) -> None:
        """Displays the `OverlayInput` widget for editing a specific cell.

        Args:
            log_entry (dict): The log entry being edited.
            col_index (int): The column index of the cell being edited.
            value (str): The current value of the cell.
            edit_mode (str): The editing mode for the overlay input
                (e.g., "date_only", "time_only", "memo").
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

        This event is triggered when the user submits input in the `OverlayInput`
        widget. It validates the input based on the `edit_mode` and updates
        the corresponding log entry field.

        Args:
            event (Input.Submitted): The event object from the submitted input.
        """
        val = event.value.strip()
        inp = cast(OverlayInput, event.control)
        if inp.edit_mode == "date_only":
            smart_date = operations.parse_smart_date(val)
            if smart_date is None:
                self.notify(
                    "Error: Invalid date format. "
                    "Examples: 03-26, 3/26, 26, today, yesterday, -1",
                    severity="error",
                )
                return
            val = smart_date
        elif inp.edit_mode == "time_only":
            # Smart parsing for time input: HH:mm, H:mm, H:m, HHMM, or H
            import re

            def parse_smart_time(s: str) -> tuple[str, int] | None:
                """Parse common time input strings into (HH:mm, day_offset)."""
                s = s.strip().replace(".", ":")
                h, mn = -1, -1

                # Handle H:M or HH:MM
                m_sep = re.match(r"^(\d{1,2}):(\d{1,2})$", s)
                if m_sep:
                    h, mn = int(m_sep.group(1)), int(m_sep.group(2))
                else:
                    # Handle HMM or HHMM
                    m_num = re.match(r"^(\d{3,4})$", s)
                    if m_num:
                        sn = m_num.group(1)
                        if len(sn) == 3:
                            h, mn = int(sn[0]), int(sn[1:])
                        else:
                            h, mn = int(sn[:2]), int(sn[2:])
                    else:
                        # Handle H or HH
                        m_h = re.match(r"^(\d{1,2})$", s)
                        if m_h:
                            h, mn = int(m_h.group(1)), 0
                        else:
                            # Fallback: Try full ISO parse
                            try:
                                dt = datetime.fromisoformat(s.replace(" ", "T"))
                                return dt.strftime("%H:%M"), 0
                            except ValueError:
                                return None

                if 0 <= h < 100 and 0 <= mn < 60:
                    offset = h // 24
                    h = h % 24
                    return f"{h:02}:{mn:02}", offset
                return None

            smart_res = parse_smart_time(val)
            if smart_res is None:
                self.notify(
                    "Error: Invalid time format. "
                    "Examples: 09:30, 9:30, 25:00, 0905, 18",
                    severity="error",
                )
                return

            val, day_offset = smart_res

            # Cross-validation: start <= end
            current_log = self._editing_log_entry
            # Target date is calculated from the log's start date
            base_date = date.fromisoformat(current_log["start_time"][:10])
            target_date = base_date + timedelta(days=day_offset)
            val = f"{target_date.isoformat()}T{val}:00"

            try:
                if self._editing_col_index == LogColumn.START_TIME:
                    st = datetime.fromisoformat(val)
                    if current_log["end_time"]:
                        et = datetime.fromisoformat(current_log["end_time"])
                        if et < st:

                            def check_adjust_end(confirm: bool | None) -> None:
                                if confirm:
                                    self._commit_log_update(
                                        current_log, start_time=val, end_time=val
                                    )

                            self.push_screen(
                                ConfirmActionModal(
                                    "Time Validation",
                                    "Start time is after end time. "
                                    "Adjust end time to match?",
                                    yes_label="Adjust (y)",
                                    no_label="Cancel (c)",
                                ),
                                check_adjust_end,
                            )
                            self._hide_edit_overlay()
                            return
                elif self._editing_col_index == LogColumn.END_TIME:
                    et = datetime.fromisoformat(val)
                    st = datetime.fromisoformat(current_log["start_time"])
                    if et < st:

                        def check_adjust_start(confirm: bool | None) -> None:
                            if confirm:
                                self._commit_log_update(
                                    current_log, start_time=val, end_time=val
                                )

                        self.push_screen(
                            ConfirmActionModal(
                                "Time Validation",
                                "End time is before start time. "
                                "Adjust start time to match?",
                                yes_label="Adjust (y)",
                                no_label="Cancel (c)",
                            ),
                            check_adjust_start,
                        )
                        self._hide_edit_overlay()
                        return
            except (ValueError, TypeError):
                # Invalid date formats or mixed types; validation handled by callers.
                pass

        if self._editing_col_index == LogColumn.DATE:
            # Update date of both start_time and end_time (preserving multi-day offset)
            if len(val) == 10:
                try:
                    new_date_obj = date.fromisoformat(val)
                    old_start_iso = self._editing_log_entry["start_time"]
                    old_end_iso = self._editing_log_entry["end_time"]

                    old_start_dt = datetime.fromisoformat(old_start_iso)
                    new_start_dt = datetime.combine(new_date_obj, old_start_dt.time())
                    new_start_iso = new_start_dt.isoformat()

                    new_end_iso = None
                    if old_end_iso:
                        old_end_dt = datetime.fromisoformat(old_end_iso)
                        day_offset_val = old_end_dt.date() - old_start_dt.date()
                        new_end_dt = datetime.combine(
                            new_date_obj + day_offset_val, old_end_dt.time()
                        )
                        new_end_iso = new_end_dt.isoformat()

                    self._commit_log_update(
                        self._editing_log_entry,
                        start_time=new_start_iso,
                        end_time=new_end_iso,
                    )
                except (ValueError, TypeError):
                    self.notify("Error updating date.", severity="error")
        elif self._editing_col_index == LogColumn.START_TIME:
            # Start Time (val is already ISO string if edit_mode was time_only)
            self._update_start_time(self._editing_log_entry, val)
        elif self._editing_col_index == LogColumn.END_TIME:
            # End Time (val is already ISO string if edit_mode was time_only)
            self._update_end_time(self._editing_log_entry, val)
        elif self._editing_col_index == LogColumn.DURATION:
            # duration_hours
            try:
                duration = float(val) if val else None
            except ValueError:
                self.notify("Please enter a number (e.g. 2.5)", severity="error")
                return
            self._commit_log_update(self._editing_log_entry, duration_hours=duration)
        elif self._editing_col_index == LogColumn.MEMO:
            # Memo
            self._update_memo(self._editing_log_entry, val)

        self._hide_edit_overlay()

    def _hide_edit_overlay(self) -> None:
        """Hides the edit overlay and returns focus to the logs table."""
        inp = self.query_one("#edit-overlay", OverlayInput)
        inp.can_focus = False
        inp.styles.display = "none"
        self.logs_table.focus()

    def _get_selected_log_entry(self) -> dict | None:
        """Helper to get the log entry currently highlighted in the logs table."""
        if self.focused != self.logs_table:
            return None
        coord = self.logs_table.cursor_coordinate
        if not coord:
            return None
        try:
            cell_key = self.logs_table.coordinate_to_cell_key(coord)
        except (ValueError, KeyError, IndexError):
            return None
        if not cell_key or not cell_key.row_key or not cell_key.row_key.value:
            return None
        try:
            log_id = int(str(cell_key.row_key.value))
        except (ValueError, TypeError):
            return None
        return next((entry for entry in self.logs if entry["id"] == log_id), None)

    def action_undo(self) -> None:
        """Undo the last log operation."""
        try:
            undone_actions = operations.undo()
            if undone_actions:
                self.refresh_data()
                actions_str = ", ".join(undone_actions)
                self.notify(f"Undo successful! Undid: {actions_str}", title="Undo")
            else:
                self.notify("Nothing to undo.", severity="warning")
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    def action_redo(self) -> None:
        """Redo the last undone log operation."""
        try:
            redone_actions = operations.redo()
            if redone_actions:
                self.refresh_data()
                actions_str = ", ".join(redone_actions)
                self.notify(f"Redo successful! Redid: {actions_str}", title="Redo")
            else:
                self.notify("Nothing to redo.", severity="warning")
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    def action_restart_job(self) -> None:
        """Action to restart the job associated with the selected log entry.

        This clones the project and job from the currently highlighted row
        in the LogsTable and starts a new timer for it.
        """
        log_entry = self._get_selected_log_entry()
        if not log_entry:
            return

        project_name = log_entry["project_name"]
        job_name = log_entry["job_name"]
        memo = log_entry["memo"] if self.copy_memo_on_restart else ""

        self._start_log_with_config(project_name, job_name, memo)

    def action_parallel_clone_unassigned(self) -> None:
        """Clones the selected log entry in parallel as an Unassigned log."""
        log_entry = self._get_selected_log_entry()
        if not log_entry:
            return

        try:
            operations.duplicate_log(log_entry["id"], None, None)
            self.refresh_data()
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    def action_parallel_clone_assigned(self) -> None:
        """Clones the selected log entry in parallel to a selected job."""
        log_entry = self._get_selected_log_entry()
        if not log_entry:
            return

        def cb(result: tuple[str, str] | None) -> None:
            if result is None:
                return
            p_name, j_name = result
            try:
                operations.duplicate_log(log_entry["id"], p_name, j_name)
                self.refresh_data()
            except Exception as e:
                self.notify(f"Error: {e}", severity="error")

        self.push_screen(JobSelectionModal(title="Select Parallel Job"), cb)

    def _start_log_with_config(
        self, project_name: str | None, job_name: str | None, memo: str = ""
    ) -> None:
        """Helper to start a log, handling parallel tracking confirmation if needed."""
        if operations.is_any_job_running():

            def cb(res: bool | None, memo=memo) -> None:
                if res:
                    try:
                        operations.start_log(
                            project_name, job_name, memo=memo, force_parallel=True
                        )
                        self.refresh_data()
                    except Exception as e:
                        self.notify(f"Error: {e}", severity="error")

            self.push_screen(
                ConfirmActionModal(
                    "Parallel Tracking",
                    "A job is already running. Start in parallel?",
                    yes_label="Start Parallel (s)",
                    no_label="Cancel (c)",
                ),
                cb,
            )
            return

        try:
            operations.start_log(project_name, job_name, memo=memo)
            self.refresh_data()
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

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
            and self.projects_tree.cursor_node.data
            and self.projects_tree.cursor_node.data["type"] == "job"
        ):
            job_name = self.projects_tree.cursor_node.data["job_name"]
            project_name = self.projects_tree.cursor_node.data["project_name"]

            self.start_timer_for_selection((project_name, job_name))
            return

        self.push_screen(
            JobSelectionModal(title="Start New Job"), self.start_timer_for_selection
        )

    def start_timer_for_selection(self, selection: tuple[str, str] | None) -> None:
        """Starts a timer for the selected project and job.

        Args:
            selection (tuple[str, str] | None): A tuple containing
                (project_name, job_name) or None if no selection was made.
        """
        if selection is None:
            return

        project_name, job_name = selection

        self._start_log_with_config(project_name, job_name)

    def action_stop_job(self) -> None:
        """Action handler to stop a running job.

        If focused on a running log in the table, stops that specific log.
        Otherwise, stops the most recent running log.
        """
        log_id_to_stop = None
        if self.focused == self.logs_table:
            coord = self.logs_table.cursor_coordinate
            if coord:
                try:
                    cell_key = self.logs_table.coordinate_to_cell_key(coord)
                    if cell_key and cell_key.row_key:
                        log_id = int(str(cell_key.row_key.value))
                        log_entry = next(
                            (e for e in self.logs if e["id"] == log_id), None
                        )
                        if log_entry and log_entry["end_time"] is None:
                            log_id_to_stop = log_id
                except (ValueError, KeyError, IndexError, TypeError):
                    pass

        try:
            if log_id_to_stop is not None:
                operations.stop_log(log_id=log_id_to_stop)
            else:
                operations.stop_all_logs()
            self.refresh_data()
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    def action_start_unassigned(self) -> None:
        """Action handler to start an unassigned log entry."""
        self._start_log_with_config(None, None)

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

        def check_delete(confirm: bool | None) -> None:
            if confirm:
                try:
                    log_id = int(str(cell_key.row_key.value))
                    operations.delete_log(log_id)
                    self.refresh_data()
                except Exception as e:
                    self.notify(f"Error: {e}", severity="error")

        self.push_screen(ConfirmDeleteModal(), check_delete)

    def action_export_logs(self) -> None:
        """Action handler to export logs using a user-specified TOML profile."""
        from . import exporter
        from .modals import ExportLogsModal

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
                    pass
                else:
                    self.notify("No logs matched or exported.", severity="warning")
            except Exception as e:
                with open("wtl_error.log", "a") as f:
                    f.write(f"Export Error: {e}\n")
                    traceback.print_exc(file=f)
                self.notify(f"Export Error: {e} (See wtl_error.log)", severity="error")

        self.push_screen(ExportLogsModal(), handle_export)

    def action_show_summary(self) -> None:
        """Action handler to show the Daily Summary screen."""
        from .daily_summary import DailySummaryScreen

        if isinstance(self.screen, DailySummaryScreen):
            return
        self.push_screen(DailySummaryScreen())

    def action_show_dashboard(self) -> None:
        """Action handler to show the Dashboard screen."""
        from .dashboard import DashboardScreen

        if isinstance(self.screen, DashboardScreen):
            return
        self.push_screen(DashboardScreen())

    def action_show_filter(self) -> None:
        """Action handler to show the Filter modal."""
        from .modals import FilterModal

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

        self.push_screen(FilterModal(current), handle_filter)

    def action_toggle_show_archived(self) -> None:
        """Toggle the visibility of archived projects in the tree."""
        self.show_archived = not self.show_archived
        self.refresh_data()


if __name__ == "__main__":
    app = WtlApp()
    app.run()
