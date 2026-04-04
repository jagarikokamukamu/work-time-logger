"""Export Logs Modal."""

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Button, Input, Label

from .. import db
from .base import BaseModal


class ExportLogsModal(BaseModal[tuple[str, str, str]]):
    """Modal to enter file paths and date for exporting logs."""

    CSS = """
    #export-dialog {
        layout: grid;
        grid-size: 2;
        grid-gutter: 0 2;
        padding: 0 1;
        width: 60;
        height: auto;
        border: thick $background 80%;
        background: $surface;
    }
    .export-label {
        height: auto;
        content-align: right middle;
    }
    #export-profile, #export-output, #export-date {
        width: 100%;
        height: auto;
        border: none;
        background: $surface;
        border-bottom: solid $accent;
        padding: 0 1;
    }
    #export-profile:focus, #export-output:focus, #export-date:focus {
       border-bottom: double $secondary;
    }
    .dialog-buttons {
        width: 100%;
        height: auto;
        border: none;
    }
    """

    BINDINGS = [
        ("escape", "dismiss_modal", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the export dialog widgets."""
        from datetime import date

        yield Container(
            Label("Profile (.toml):", classes="export-label"),
            Input(value=str(db.DB_DIR / "profile.toml"), id="export-profile"),
            Label("Date (YYYY-MM-DD):", classes="export-label"),
            Input(value=date.today().isoformat(), id="export-date"),
            Label("Output CSV Path:", classes="export-label"),
            Input(value="report.csv", id="export-output"),
            Button(
                "Cancel", variant="error", id="btn-cancel", classes="dialog-buttons"
            ),
            Button(
                "Export", variant="success", id="btn-export", classes="dialog-buttons"
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
