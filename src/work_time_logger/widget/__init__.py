"""Widget package for Work Time Logger.

Provides desktop widgets to track tasks outside of the terminal.
"""


def run_widget():
    """Start the Flet desktop widget."""
    import flet as ft

    from .app import main

    ft.app(target=main)
