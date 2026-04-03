"""Jump to Date Modal."""

from textual import on
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Input, Static

from .. import operations
from .base import BaseModal


class JumpToDateModal(BaseModal[str | None]):
    """Modal to enter a date to jump to in the Daily Summary."""

    CSS = """
    #jump-dialog {
        width: 40;
    }
    #jump-input {
        margin-top: 1;
        width: 100%;
    }
    """

    def __init__(self, initial_date: str, **kwargs):
        super().__init__(**kwargs)
        self.initial_date = initial_date

    def compose(self) -> ComposeResult:
        """Compose the jump to date dialog."""
        with Container(id="jump-dialog", classes="modal-container"):
            yield Static("Jump to Date", classes="modal-title")
            yield Input(
                value=self.initial_date,
                placeholder="YYYY-MM-DD, today, yesterday, -1, etc.",
                id="jump-input",
            )

    def on_mount(self) -> None:
        """Focus the input on mount."""
        self.query_one("#jump-input").focus()

    @on(Input.Submitted, "#jump-input")
    def on_date_submitted(self, event: Input.Submitted) -> None:
        """Handle date input submission."""
        event.stop()
        val = event.value.strip()
        smart_date = operations.parse_smart_date(val)

        if smart_date:
            self.dismiss(smart_date)
        else:
            self.app.notify(f"Invalid date: {val}", severity="error")
