"""Job Code Expansion Modal."""

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, DataTable, Input, Label, Static

from .. import db, exporter, operations
from .base import BaseModal


class JobCodeModal(BaseModal):
    """A modal screen that displays the job code expansion for a specific job."""

    CSS = """
    #job-code-container {
        width: 100;
        height: 80%;
        border: thick $background 80%;
        background: $surface;
    }
    .section-label {
        width: 100%;
        text-style: bold;
        background: $accent;
        color: $text;
        padding: 0 1;
        margin-top: 1;
    }
    #attributes-table {
        height: 1fr;
        border: none;
    }
    #preview-table {
        height: 1fr;
        border: none;
        background: $boost;
    }
    #btn-close {
        margin-top: 1;
        width: 100%;
        border: none;
    }
    #edit-section {
        margin-top: 1;
        display: none;
        height: auto;
        border: tall $accent;
        padding: 0 1;
    }
    #edit-label {
        width: 25;
        content-align: left middle;
        text-style: bold;
    }
    #job-code-edit-input {
        width: 1fr;
        height: auto;
        border: none;
    }
    """

    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    def __init__(self, project_name: str, job_name: str, **kwargs):
        super().__init__(**kwargs)
        self.project_name = project_name
        self.job_name = job_name
        self.import_row = {}
        self.name_vars = []
        self._editing_col_name = None

    def compose(self) -> ComposeResult:
        """Compose the job code expansion screen widgets."""
        with Container(id="job-code-container", classes="modal-container"):
            yield Static(id="job-code-title", classes="modal-title")

            yield Label("Attributes (Edit by Enter)", classes="section-label")
            yield DataTable(id="attributes-table", cursor_type="cell")

            yield Label("Export Preview", classes="section-label")
            yield DataTable(id="preview-table", cursor_type="cell")

            with Horizontal(id="edit-section"):
                yield Label("Edit:", id="edit-label")
                yield Input(id="job-code-edit-input")
            yield Button("Close", id="btn-close", variant="primary")

    def on_mount(self) -> None:
        """Mount handler to populate the job code table."""
        self.refresh_table()

    def action_toggle_mode(self) -> None:
        """N/A - Toggle mode is removed in favor of integrated view."""
        pass

    def refresh_table(self) -> None:
        """Update both attributes and preview tables."""
        attr_table = self.query_one("#attributes-table", DataTable)
        prev_table = self.query_one("#preview-table", DataTable)

        attr_table.clear(columns=True)
        attr_table.add_columns("Attribute", "Value")

        prev_table.clear(columns=True)
        prev_table.add_columns("Export Column", "Preview Value")

        title = self.query_one("#job-code-title", Static)
        title.update(f"Job Details: {self.job_name}")

        try:
            self._refresh_import_mode(attr_table)
            self._refresh_export_mode(prev_table)
        except Exception as e:
            attr_table.add_row("Error", str(e))

        # Focus attributes table if nothing is focused or returning from edit
        if self.focused not in (attr_table, prev_table):
            attr_table.focus()

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
        """Handle cell selection for editing in Attributes table."""
        if event.control.id != "attributes-table":
            return
        event.stop()

        # Ensure we are in the "Value" column (index 1)
        if event.coordinate.column != 1:
            return

        row_key = event.cell_key.row_key.value
        if not row_key:
            return

        # Protection: Cannot edit variables that are part of the Job Name
        if row_key in self.name_vars:
            self.app.notify(
                "Job名は直接編集できません (プロジェクト設定に依存します)",
                severity="warning"
            )
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
        self.query_one("#attributes-table").focus()

    def on_key(self, event) -> None:
        """Handle escape to cancel editing."""
        if event.key == "escape":
            inp = self.query_one("#job-code-edit-input")
            if inp.has_focus:
                event.stop()
                self.query_one("#edit-section").styles.display = "none"
                self.query_one("#attributes-table").focus()
                return
        # Default behavior: ModalScreen handles escape to dismiss if not caught above.

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        event.stop()
        if event.button.id == "btn-close":
            self.dismiss()
