"""Help Modal."""

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static

from .base import BaseModal


class HelpModal(BaseModal):
    """A modal screen that displays a list of all commands."""

    CSS = """
    #help-container {
        width: 70;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the help screen contents."""
        with Container(id="help-container", classes="modal-container"):
            yield Static("WTL Keyboard Shortcuts", classes="modal-title")
            yield Static(
                "Global Commands:\n"
                "  h, f1   : Show this detailed help message\n"
                "  tab     : Switch focus between Sidebar and Main Content\n"
                "  q       : Quit application\n"
                "  s       : Search / Start a new job\n"
                "  shift+s : Start unassigned timer\n"
                "  shift+a : Add empty log\n"
                "  x       : Stop tracking current job\n"
                "  e       : Export logs to CSV\n"
                "  v       : View Daily Summary (aggregates hours)\n"
                "  d       : View Dashboard (Weekly/Monthly charts)\n"
                "  f       : Filter logs by Project, Job, or Date Range\n"
                "\nSidebar Focus (Projects & Jobs):\n"
                "  enter   : Start selected job\n"
                "  a       : Add log pre-assigned to selected job\n"
                "\nMain List Focus (Logs):\n"
                "  enter   : Edit selected cell (Date, Time, Memo, or Duration)\n"
                "  shift+d : Delete selected log\n"
                "  r       : Restart (clone) selected job\n"
                "\nEdit Mode:\n"
                "  enter   : Save changes\n"
                "  esc     : Cancel edit\n"
                "  up/down : Adjust values for date/time fields"
            )

    def on_key(self, event) -> None:
        """Dismiss the modal on any key press."""
        self.dismiss()
