"""Confirm Delete Modal."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, Label, Static

from .base import BaseModal


class ConfirmDeleteModal(BaseModal[bool]):
    """Modal to confirm log deletion."""

    CSS = """
    #confirm-dialog {
        padding: 0;
        width: 50;
        height: auto;
        border: thick $background 80%;
        background: $surface;
    }
    #question {
        width: 100%;
        content-align: center middle;
        padding: 1 2;
    }
    .modal-title {
        width: 100%;
        content-align: center middle;
        height: 1;
        background: $error;
        color: $text;
        text-style: bold;
        margin-bottom: 0;
    }
    #button-row {
        width: 100%;
        height: auto;
        padding: 0 1 1 1;
    }
    Button {
        width: 1fr;
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("d", "yes", "Delete"),
        ("c", "no", "Cancel"),
        ("escape", "no", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the confirmation dialog widgets."""
        with Container(id="confirm-dialog", classes="modal-container"):
            yield Static("Confirm Delete", classes="modal-title")
            yield Label("Are you sure you want to delete this log?", id="question")
            with Horizontal(id="button-row"):
                yield Button("Delete (d)", variant="error", id="yes")
                yield Button("Cancel (c)", variant="primary", id="no")

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
