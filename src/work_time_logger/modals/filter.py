"""Filter Modal."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, Input, Static

from .base import BaseModal


class FilterModal(BaseModal):
    """A modal screen for filtering logs by project, job, and date range."""

    CSS = """
    #filter-container {
        width: 60;
    }
    .filter-label {
        margin-top: 1;
        text-style: bold;
    }
    .filter-buttons {
        margin-top: 2;
        height: 3;
        align: right middle;
    }
    .filter-btn {
        margin-left: 1;
        margin-right: 1;
    }
    """

    def __init__(self, current_filters: dict, **kwargs):
        super().__init__(**kwargs)
        self.current_filters = current_filters

    def compose(self) -> ComposeResult:
        """Compose the filter dialog widgets."""
        with Container(id="filter-container", classes="modal-container"):
            yield Static("Filter Logs", classes="modal-title")

            yield Static("Project Name:", classes="filter-label")
            yield Input(
                value=self.current_filters.get("project") or "",
                id="f-project",
                placeholder="None",
            )

            yield Static("Job Name:", classes="filter-label")
            yield Input(
                value=self.current_filters.get("job") or "",
                id="f-job",
                placeholder="None",
            )

            yield Static("Start Date (YYYY-MM-DD):", classes="filter-label")
            yield Input(
                value=self.current_filters.get("start") or "",
                id="f-start",
                placeholder="None",
            )

            yield Static("End Date (YYYY-MM-DD):", classes="filter-label")
            yield Input(
                value=self.current_filters.get("end") or "",
                id="f-end",
                placeholder="None",
            )

            with Horizontal(classes="filter-buttons"):
                yield Button(
                    "Clear", id="btn-clear", variant="error", classes="filter-btn"
                )
                yield Button("Cancel", id="btn-cancel", classes="filter-btn")
                yield Button(
                    "Apply", id="btn-apply", variant="primary", classes="filter-btn"
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle filter dialog button presses."""
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-clear":
            self.dismiss({"project": None, "job": None, "start": None, "end": None})
        elif event.button.id == "btn-apply":
            res = {
                "project": self.query_one("#f-project", Input).value.strip() or None,
                "job": self.query_one("#f-job", Input).value.strip() or None,
                "start": self.query_one("#f-start", Input).value.strip() or None,
                "end": self.query_one("#f-end", Input).value.strip() or None,
            }
            self.dismiss(res)
