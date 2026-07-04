from .cli import app
from .db import init_db


def main() -> None:
    """Entry point for the command-line interface."""
    init_db()
    app()


