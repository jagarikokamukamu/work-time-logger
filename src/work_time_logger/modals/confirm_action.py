"""Confirm Action Modal."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, Label, Static

from .base import BaseModal


class ConfirmActionModal(BaseModal[bool]):
    """Generic modal to confirm an action."""

    CSS = """
    #confirm-action-dialog {
        padding: 0;
        width: 60;
        height: auto;
        border: thick $background 80%;
        background: $surface;
    }
    #action-question {
        width: 100%;
        content-align: center middle;
        padding: 1 2;
    }
    .modal-title {
        width: 100%;
        content-align: center middle;
        height: 1;
        background: $accent;
        color: $text;
        text-style: bold;
        margin-bottom: 0;
    }
    #action-button-row {
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
        ("y", "yes", "Yes"),
        ("s", "yes", "Start"),
        ("n", "no", "No"),
        ("c", "no", "Cancel"),
        ("escape", "no", "Cancel"),
    ]

    def __init__(
        self,
        title: str,
        question: str,
        yes_label: str = "Yes (y)",
        no_label: str = "No (n)",
        **kwargs,
    ):
        """Initialize the Confirm Action modal.

        Args:
            title (str): Title for the dialog.
            question (str): The main question text to display.
            yes_label (str): Label for the 'Yes' button.
            no_label (str): Label for the 'No' button.
            **kwargs: Additional widget arguments.
        """
        super().__init__(**kwargs)
        self.dialog_title = title
        self.dialog_question = question
        self.yes_label = yes_label
        self.no_label = no_label

    def compose(self) -> ComposeResult:
        """Compose the confirmation dialog widgets."""
        with Container(id="confirm-action-dialog", classes="modal-container"):
            yield Static(self.dialog_title, classes="modal-title")
            yield Label(self.dialog_question, id="action-question")
            with Horizontal(id="action-button-row"):
                yield Button(self.yes_label, variant="warning", id="yes")
                yield Button(self.no_label, variant="primary", id="no")

    def action_yes(self) -> None:
        """Action handler for 'Yes' response."""
        self.dismiss(True)

    def action_no(self) -> None:
        """Action handler for 'No' response."""
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events (Yes/No)."""
        if event.button.id == "yes":
            self.dismiss(True)
        else:
            self.dismiss(False)
