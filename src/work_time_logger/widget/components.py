"""UI Components for WTL desktop widget."""

import flet as ft


class ActiveTaskContainer(ft.Container):
    """Semi-transparent container displaying the active task name and timer."""

    def __init__(self, on_close_click):
        """Initializes the container.

        Args:
            on_close_click: Event handler for the close button click.
        """
        # Two icons toggled via visibility toggle.
        # ft.Icon.name assignment does not propagate in Flet 0.85.
        self.icon_idle = ft.Icon(
            ft.Icons.COFFEE_ROUNDED, color=ft.Colors.WHITE_70, size=24, visible=True
        )
        self.icon_running = ft.Icon(
            ft.Icons.TIMER_ROUNDED, color=ft.Colors.WHITE_70, size=24, visible=False
        )

        self.job_text = ft.Text(
            "Idle",
            size=12,
            color=ft.Colors.WHITE_70,
            weight=ft.FontWeight.BOLD,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
        self.time_text = ft.Text(
            "00:00:00",
            size=16,
            color="#ff4444",
            weight=ft.FontWeight.BOLD,
        )

        self.close_icon = ft.Icon(
            ft.Icons.CLOSE_ROUNDED,
            color=ft.Colors.WHITE,
            size=12,
            opacity=0.3,
            animate_opacity=ft.Animation(100, ft.AnimationCurve.EASE_OUT),
        )

        # Use Container to smoothly transition background color
        self.close_button = ft.Container(
            content=self.close_icon,
            width=20,
            height=20,
            border_radius=4,
            bgcolor=ft.Colors.TRANSPARENT,
            animate=ft.Animation(100, ft.AnimationCurve.EASE_OUT),
            on_hover=self._on_close_hover,  # type: ignore[reportArgumentType]
            on_click=on_close_click,
            tooltip="Close Widget",
        )

        super().__init__(
            content=ft.Row(
                [
                    ft.Row(
                        [
                            ft.Stack(
                                [self.icon_idle, self.icon_running],
                                width=24,
                                height=24,
                            ),
                            ft.Column(
                                [self.job_text, self.time_text],
                                spacing=1,
                                alignment=ft.MainAxisAlignment.CENTER,
                            ),
                        ],
                        spacing=10,
                    ),
                    self.close_button,
                ],
                spacing=10,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=ft.Padding.symmetric(horizontal=14, vertical=10),
            bgcolor="#121214e6",  # 90% opacity dark grey
            border_radius=12,
            border=ft.Border.all(1, ft.Colors.WHITE_10),
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=8,
                color=ft.Colors.BLACK_45,
                offset=ft.Offset(0, 4),
            ),
        )

    def update_state(self, is_running: bool, job_name: str = "", time_str: str = ""):
        """Update visual state based on the active tracking status."""
        if is_running:
            self.job_text.value = job_name
            self.time_text.value = time_str
            self.time_text.color = ft.Colors.WHITE_70
            self.icon_idle.visible = False
            self.icon_running.visible = True
        else:
            self.job_text.value = "Idle"
            self.time_text.value = "No active job"
            self.time_text.color = "#ff4444"
            self.icon_idle.visible = True
            self.icon_running.visible = False

    def _on_close_hover(self, e: ft.ControlEvent) -> None:
        """Smoothly transitions color on close button hover."""
        is_hover = e.data == "true" or e.data is True
        self.close_icon.opacity = 1.0 if is_hover else 0.3
        self.close_button.bgcolor = ft.Colors.RED if is_hover else ft.Colors.TRANSPARENT
        self.close_icon.update()
        self.close_button.update()
