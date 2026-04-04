"""Job Code Expansion Modal."""

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, DataTable, Input, Label, Static

from .. import db, exporter, operations
from ..widgets import CopyableDataTable
from .base import BaseModal


class JobCodeModal(BaseModal):
    """A modal screen that displays the job code expansion for a specific job."""

    CSS = """
    #job-code-container {
        width: 80;
        border: none;
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
        width: 20;
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
        with Container(id="job-code-container", classes="modal-container"):
            yield Static(id="job-code-title", classes="modal-title")
            yield CopyableDataTable(id="job-code-table", cursor_type="cell")
            yield Label(
                "[b orange]c[/] copy  [b orange]t[/] toggle", classes="copy-hint"
            )
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
