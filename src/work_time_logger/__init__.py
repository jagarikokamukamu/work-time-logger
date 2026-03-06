from .cli import app
from .db import init_db

def main() -> None:
    init_db()
    app()

def tui_main() -> None:
    init_db()
    from .tui import WtlApp
    app = WtlApp()
    app.run()
