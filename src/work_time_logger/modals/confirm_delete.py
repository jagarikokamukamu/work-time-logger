"""Confirm Delete Modal."""

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Button, Label

from .base import BaseModal


class ConfirmDeleteModal(BaseModal[bool]):
    """Modal to confirm log deletion."""

    CSS = """
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
    ]

    def compose(self) -> ComposeResult:
        """Compose the confirmation dialog widgets."""
        yield Container(
            Label("Are you sure you want to delete this log?", id="question"),
            Button("Yes (y)", variant="error", id="yes"),
            Button("No (n)", variant="primary", id="no"),
            id="confirm-dialog",
        )

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
