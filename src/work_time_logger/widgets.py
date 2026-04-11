"""Custom widgets and modals for the Work Time Logger TUI."""

from datetime import datetime, timedelta

from rich.text import Text
from textual.binding import Binding
from textual.widgets import (
    DataTable,
    Input,
    Static,
)


class CopyableDataTable(DataTable):
    """A DataTable that supports copying the selected row or cell to the clipboard."""

    BINDINGS = [
        Binding("c", "copy_to_clipboard", "コピー", show=True),
        Binding("enter", "select_cursor", "編集", show=True),
    ]

    def action_copy_to_clipboard(self) -> None:
        """Copies the currently selected item to the clipboard."""
        coord = self.cursor_coordinate
        if not coord:
            return

        try:
            if self.cursor_type == "row":
                row_key = self.coordinate_to_cell_key(coord).row_key
                row_vals = self.get_row(row_key)
                text = "\t".join(str(v) for v in row_vals)
            elif self.cursor_type == "column":
                col_key = self.coordinate_to_cell_key(coord).column_key
                col_vals = self.get_column(col_key)
                text = "\n".join(str(v) for v in col_vals)
            else:
                val = self.get_cell_at(coord)
                text = str(val)

            self.app.copy_to_clipboard(text)
        except Exception as e:
            self.app.notify(f"コピーに失敗しました: {e}", severity="error")


class OverlayInput(Input):
    """An input field that overlays a DataTable cell for in-place editing."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("up", "increment", "Increment D/T"),
        ("down", "decrement", "Decrement D/T"),
        ("enter", "submit", "Save"),  # For footer display
        ("tab", "cancel", "Cancel"),
        ("shift+tab", "cancel", "Cancel"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.edit_mode = "memo"  # "memo", "date_only", "time_only", "duration"
        self.duration_step = 0.1

    def action_cancel(self) -> None:
        """Dismiss and hide the overlay input."""
        self.can_focus = False
        self.styles.display = "none"
        # If we are in a modal, we might want to focus the modal's table.
        # Otherwise, default to the main app table.
        try:
            self.screen.query_one(DataTable).focus()
        except Exception:
            self.app.query_one(DataTable).focus()

    def action_increment(self) -> None:
        """Increment the current field value."""
        self._adjust_value(1)

    def action_decrement(self) -> None:
        """Decrement the current field value."""
        self._adjust_value(-1)

    def _adjust_value(self, delta: int) -> None:
        """Adjust the current input value based on the edit mode and delta.

        This handles incrementing/decrementing dates, times, and durations
        using arrow keys.

        Args:
            delta (int): The amount to adjust (typically 1 or -1).
        """
        if self.edit_mode == "memo":
            return

        cursor_pos = self.cursor_position
        val = self.value

        try:
            if self.edit_mode == "date_only":
                # YYYY-MM-DD
                dt = datetime.strptime(val, "%Y-%m-%d")
                if cursor_pos <= 4:
                    dt = dt.replace(year=max(1, dt.year + delta))
                elif cursor_pos <= 7:
                    # Move month
                    month = dt.month + delta
                    year = dt.year
                    while month > 12:
                        month -= 12
                        year += 1
                    while month < 1:
                        month += 12
                        year -= 1
                    # Ensure day is valid for new month
                    import calendar

                    last_day = calendar.monthrange(year, month)[1]
                    dt = dt.replace(year=year, month=month, day=min(dt.day, last_day))
                else:
                    dt += timedelta(days=delta)
                self.value = dt.strftime("%Y-%m-%d")

            elif self.edit_mode == "time_only":
                # HH:mm:ss or YYYY-MM-DD HH:mm:ss
                if "T" in val:
                    val = val.replace("T", " ")
                if " " in val:
                    # Parse full ISO
                    dt = datetime.fromisoformat(val)
                    if cursor_pos <= 10:  # Date part
                        dt += timedelta(days=delta)
                    elif cursor_pos <= 13:  # HH
                        dt += timedelta(hours=delta)
                    elif cursor_pos <= 16:  # mm
                        dt += timedelta(minutes=delta)
                    else:  # ss
                        dt += timedelta(seconds=delta)
                    self.value = dt.isoformat(sep=" ")
                else:
                    # Simple HH:mm
                    parts = val.split(":")
                    if len(parts) != 2:
                        return
                    try:
                        h, m = int(parts[0]), int(parts[1])
                        if cursor_pos <= len(parts[0]):
                            h += delta
                        else:
                            m += delta

                        total_mins = h * 60 + m
                        total_mins = max(0, total_mins)
                        nh, nm = divmod(total_mins, 60)
                        self.value = f"{nh:02}:{nm:02}"
                    except ValueError:
                        pass

            elif self.edit_mode == "duration":
                # Float hours, increment by duration_step
                try:
                    curr_val = float(val) if val.strip() else 0.0
                    new_val = max(0.0, curr_val + (delta * self.duration_step))
                    # Round to 2 decimal places to avoid float precision issues
                    self.value = str(round(new_val, 2))
                except ValueError:
                    pass

            elif self.edit_mode == "date":  # Legacy fallback
                dt = datetime.fromisoformat(val)
                dt += timedelta(seconds=delta)
                self.value = dt.isoformat(sep=" ")

            self.cursor_position = cursor_pos
        except (ValueError, TypeError, AttributeError):
            # Ignore transient UI errors during rapid cursor/value adjustment.
            pass


class TimelineVisualizer(Static):
    """A widget that visualizes work intervals on a 0-24h timeline."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.intervals = []  # List of (start_iso, end_iso, color)

    def set_intervals(self, intervals: list[tuple[str, str, str]]) -> None:
        """Update the intervals to display."""
        self.intervals = intervals
        self.refresh()

    def render(self) -> Text:
        """Render the 24-hour timeline bar.

        Overlapping intervals (prorated time) are visually indicated.
        """
        bar_width = 48
        cell_colors = [[] for _ in range(bar_width)]

        for start_iso, end_iso, color in self.intervals:
            if not start_iso or not end_iso:
                continue
            try:
                s = datetime.fromisoformat(start_iso)
                e = datetime.fromisoformat(end_iso)

                start_f = s.hour + s.minute / 60.0 + s.second / 3600.0
                end_f = e.hour + e.minute / 60.0 + e.second / 3600.0

                start_idx = int(start_f * (bar_width / 24.0))
                end_idx = int(end_f * (bar_width / 24.0))

                # Make sure we color at least one block if it's a very short log
                if end_idx == start_idx and start_idx < bar_width:
                    cell_colors[start_idx].append(color)
                else:
                    for i in range(start_idx, min(end_idx, bar_width)):
                        cell_colors[i].append(color)
            except (ValueError, TypeError):
                continue

        text = Text()
        for colors in cell_colors:
            if not colors:
                text.append(" ", style="on #2e2e2e")
            elif len(colors) == 1:
                col = colors[0] if colors[0] else "#79a8a8"
                text.append(" ", style=f"on {col}")
            else:
                unique_colors = list(
                    dict.fromkeys(colors)
                )  # preserve order, make unique
                col1 = unique_colors[0] if unique_colors[0] else "#79a8a8"
                if len(unique_colors) == 2:
                    col2 = unique_colors[1] if unique_colors[1] else "#79a8a8"
                    # Upper half (fg) is col1, lower half (bg) is col2
                    text.append("▀", style=f"{col1} on {col2}")
                elif len(unique_colors) > 2:
                    col2 = unique_colors[1] if unique_colors[1] else "#79a8a8"
                    # 3 or more: Use a triple-bar indicating multiple layers
                    text.append("☰", style=f"{col1} on {col2}")
                else:
                    text.append("▀", style=f"{col1} on {col1}")

        ruler_str = (
            "0" + " " * 10 + "6" + " " * 11 + "12" + " " * 11 + "18" + " " * 9 + "24"
        )
        ruler = Text("\n" + ruler_str, style="#585858")
        return text + ruler
