from .cli import app
from .db import init_db


def main() -> None:
    """Entry point for the command-line interface."""
    init_db()
    app()


def tui_main() -> None:
    """Entry point for the Textual user interface."""
    init_db()
    from .tui import WtlApp

    app = WtlApp()
    app.run()
