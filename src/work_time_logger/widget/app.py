"""Application lifecycle and main windows for WTL desktop widget."""

import flet as ft

from .components import ActiveTaskContainer
from .controller import TaskController


async def main(page: ft.Page):
    """Main entry point for the Flet application."""
    page.title = "WTL Desktop Widget"
    page.window.always_on_top = True
    page.window.frameless = True
    page.window.bgcolor = ft.Colors.TRANSPARENT
    page.bgcolor = ft.Colors.TRANSPARENT
    page.window.width = 300
    page.window.height = 70
    page.window.resizable = False
    page.padding = 0

    # Create controller
    controller = TaskController()

    # Shared shutdown routine
    def shutdown():
        controller.is_monitoring = False
        page.run_task(page.window.destroy)

    # Create UI components with close button callback
    widget_ui = ActiveTaskContainer(on_close_click=lambda _: shutdown())

    # Wrap in WindowDragArea to support window movement
    drag_area = ft.WindowDragArea(widget_ui)
    page.add(drag_area)

    # Keyboard shortcut for close (Esc / Q)
    def handle_keyboard(e):
        if e.key in ("Escape", "Q", "q"):
            shutdown()

    page.on_keyboard_event = handle_keyboard

    # Prevent close to clean up background threads gracefully
    def handle_window_event(e):
        if e.data == "close":
            shutdown()

    page.window.prevent_close = True
    page.on_window_event = handle_window_event  # type: ignore[reportAttributeAccessIssue]

    # Start database monitoring thread
    controller.start_monitoring(page, widget_ui)
