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

    # Background animation task running inside Flet's event loop
    async def animate_background():
        import asyncio
        import colorsys
        import math

        # Configuration for the chill gradient animation
        COLOR_SPEED = 0.006
        ROTATION_SPEED = 0.02
        UPDATE_INTERVAL = 0.1  # Seconds (10 FPS)
        OPACITY_HEX = "99"  # 60% opacity

        h1 = 0.0
        rot = 0.0
        try:
            while True:
                if widget_ui.is_idle:
                    # Clear bgcolor to ensure gradient is visible
                    widget_ui.bgcolor = None

                    # Generate two chill, low-brightness/moderate-saturation colors
                    c1_rgb = colorsys.hsv_to_rgb(h1, 0.6, 0.45)
                    c2_rgb = colorsys.hsv_to_rgb((h1 + 0.3) % 1.0, 0.5, 0.35)

                    r1, g1, b1 = (int(x * 255) for x in c1_rgb)
                    r2, g2, b2 = (int(x * 255) for x in c2_rgb)
                    c1 = f"#{r1:02x}{g1:02x}{b1:02x}{OPACITY_HEX}"
                    c2 = f"#{r2:02x}{g2:02x}{b2:02x}{OPACITY_HEX}"

                    widget_ui.gradient = ft.LinearGradient(
                        begin=ft.Alignment(-1.0, -1.0),
                        end=ft.Alignment(1.0, 1.0),
                        colors=[c1, c2],
                        rotation=rot,
                    )
                    widget_ui.update()
                    page.update()

                    h1 = (h1 + COLOR_SPEED) % 1.0
                    rot = (rot + ROTATION_SPEED) % (2 * math.pi)

                await asyncio.sleep(UPDATE_INTERVAL)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

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

    # Start background animation loop
    page.run_task(animate_background)
