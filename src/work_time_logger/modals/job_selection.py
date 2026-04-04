"""Job Selection Modal."""

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Input, Label, OptionList
from textual.widgets.option_list import Option

from .. import operations
from .base import BaseModal


class JobSelectionModal(BaseModal[tuple[str, str]]):
    """Modal to fuzzy search and select a job to start."""

    CSS = """
    #dialog {
        width: 60;
        height: 25;
        border: thick $background 80%;
        background: $surface;
        padding: 0;
    }
    #title {
        width: 100%;
        content-align: center middle;
        height: 1;
        background: $primary;
        color: $text;
        text-style: bold;
        margin-bottom: 1;
    }
    #search {
        margin: 0 2;
        height: auto;
        border: none;
        border-bottom: solid $accent;
        padding: 0 1;
        background: $surface;
    }
    #search:focus {
        border-bottom: double $secondary;
    }
    #job-list {
        margin: 1 2;
        height: 15;
        border: none;
        background: $surface;
    }
    """

    BINDINGS = [
        ("escape", "dismiss_modal", "Cancel"),
    ]

    def __init__(self, title: str = "Select Job"):
        super().__init__()
        self.jobs = []
        self.modal_title = title
        for p in operations.list_projects():
            for j in operations.list_jobs(p["name"]):
                self.jobs.append((p["name"], j["name"]))

    def compose(self) -> ComposeResult:
        """Compose the child widgets for the modal."""
        yield Container(
            Label(self.modal_title, id="title"),
            Input(placeholder="Type to search for a job...", id="search"),
            OptionList(id="job-list"),
            id="dialog",
            classes="modal-container",
        )

    def on_mount(self) -> None:
        """Mount handler to initialize the option list."""
        self.update_options("")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input change events to filter the job list."""
        self.update_options(event.value)

    def update_options(self, search_term: str) -> None:
        """Filter the job options based on a search term."""
        option_list = self.query_one(OptionList)
        option_list.clear_options()
        term = search_term.lower()
        for i, (p_name, j_name) in enumerate(self.jobs):
            label = f"{j_name} ({p_name})"
            if term in label.lower():
                option_list.add_option(Option(prompt=label, id=str(i)))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle selection of a job from the option list."""
        if event.option_id is not None:
            idx = int(event.option_id)
            selected_project, selected_job = self.jobs[idx]
            self.dismiss((selected_project, selected_job))
