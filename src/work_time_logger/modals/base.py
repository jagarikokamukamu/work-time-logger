"""Base Modal Screen and shared styles."""

from textual.screen import ModalScreen


class BaseModal[ModalResult](ModalScreen[ModalResult]):
    """Base class for all modal screens in WTL.

    Provides common CSS for centering, semi-transparent backgrounds,
    and standard keyboard bindings (escape/q) to dismiss the modal.
    """

    DEFAULT_CSS = """
    BaseModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    /* Common modal container styling */
    .modal-container {
        width: 60;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    /* Standard title styling for modals */
    .modal-title {
        content-align: center middle;
        width: 100%;
        text-style: bold;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        ("escape", "dismiss_modal", "Close"),
        ("q", "dismiss_modal", "Close"),
    ]

    def action_dismiss_modal(self) -> None:
        """Standard action to dismiss the modal with None."""
        self.dismiss(None)
