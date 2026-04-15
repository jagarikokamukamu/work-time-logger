"""Unit tests for the Textual TUI using pytest and textual.testing."""

from datetime import datetime
from pathlib import Path

import pytest
from textual.widgets import DataTable, Tree

from work_time_logger import db, operations
from work_time_logger.tui import WtlApp


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path: Path):
    """Override the database path to use a temporary directory for tests."""
    test_db_dir = tmp_path / ".wtl_test"
    test_db_dir.mkdir()

    original_db_dir = db.DB_DIR
    original_db_path = db.DB_PATH

    db.DB_DIR = test_db_dir
    db.DB_PATH = test_db_dir / "wtl.db"

    operations.setup()

    yield

    db.DB_DIR = original_db_dir
    db.DB_PATH = original_db_path


@pytest.mark.asyncio
async def test_tui_startup_population():
    """Test that TUI correctly populates projects and logged data on startup."""
    operations.add_project("Test Project")
    operations.add_job("Test Job", "Test Project")
    operations.start_log("Test Project", "Test Job")
    operations.stop_all_logs()

    app = WtlApp()
    async with app.run_test(size=(120, 60)):
        tree = app.query_one(Tree)
        table = app.query_one(DataTable)

        # Check tree
        assert len(tree.root.children) == 1
        assert str(tree.root.children[0].label) == "Test Project"

        # Check table
        assert table.row_count == 1
        row = table.get_row_at(0)
        assert len(row) == 8
        assert str(row[1]) == "Test Project"
        assert str(row[2]) == "Test Job"
        assert str(row[3]) == datetime.now().strftime("%Y-%m-%d")


@pytest.mark.asyncio
async def test_tui_add_empty_log():
    """Test creating an empty log via 'A' keybind."""
    app = WtlApp()
    async with app.run_test(size=(120, 60)) as pilot:
        await pilot.press("A")
        await pilot.pause()

        table = app.query_one(DataTable)
        assert table.row_count == 1
        row = table.get_row_at(0)
        assert str(row[1]) == "[未割り当て]"
        assert str(row[2]) == "[未割り当て]"


@pytest.mark.asyncio
async def test_tui_edit_log_cell():
    """Test editing an existing log's time via in-place overlay input."""
    operations.add_project("NewProj")
    operations.add_job("NewJob", "NewProj")
    lid = operations.create_empty_log()
    # Ensure end_time is late enough to avoid validation errors
    today = datetime.now().strftime("%Y-%m-%d")
    operations.update_log(lid, end_time=f"{today}T23:59:59")

    app = WtlApp()
    async with app.run_test(size=(120, 60)) as pilot:
        table = app.query_one(DataTable)
        app.set_focus(table)

        # Move to Start Time column (index 4)
        table.move_cursor(row=0, column=4)
        await pilot.press("enter")
        await pilot.pause(0.1)

        overlay = app.query_one("#edit-overlay")
        assert overlay.styles.display == "block"
        assert app.focused == overlay

        # Set value simulation (now HH:mm)
        overlay.value = "12:34"

        await pilot.press("enter")
        await pilot.pause(0.1)

        assert overlay.styles.display == "none"
        assert app.focused == table

        logs = operations.list_logs()
        # Today's date + T + 12:34:00
        today = datetime.now().strftime("%Y-%m-%d")
        assert logs[0]["start_time"] == f"{today}T12:34:00"


@pytest.mark.asyncio
async def test_tui_confirm_delete_modal():
    """Test ConfirmDeleteModal cancellation and confirmation."""
    operations.create_empty_log()
    app = WtlApp()
    async with app.run_test(size=(120, 60)) as pilot:
        table = app.query_one(DataTable)
        app.set_focus(table)
        table.move_cursor(row=0, column=0)

        # Press 'D' to trigger delete
        await pilot.press("D")
        await pilot.pause()

        from work_time_logger.modals import ConfirmDeleteModal

        assert isinstance(app.screen, ConfirmDeleteModal)

        # Cancel with 'c'
        await pilot.press("c")
        await pilot.pause()
        assert not isinstance(app.screen, ConfirmDeleteModal)
        assert len(operations.list_logs()) == 1

        # Trigger again and confirm with 'd'
        await pilot.press("D")
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()

        assert len(operations.list_logs()) == 0


@pytest.mark.asyncio
async def test_tui_filtering():
    """Test the FilterModal and filtering logic."""
    operations.add_project("P1")
    operations.add_job("J1", "P1")
    operations.start_log("P1", "J1")
    operations.stop_all_logs()

    operations.add_project("P2")
    operations.add_job("J2", "P2")
    operations.start_log("P2", "J2")
    operations.stop_all_logs()

    app = WtlApp()
    async with app.run_test(size=(120, 60)) as pilot:
        table = app.query_one(DataTable)
        assert table.row_count == 2

        await pilot.press("f")
        await pilot.pause()

        from work_time_logger.modals import FilterModal

        assert isinstance(app.screen, FilterModal)

        await pilot.click("#f-project")
        for char in "P1":
            await pilot.press(char)

        await pilot.click("#btn-apply")
        await pilot.pause()

        assert table.row_count == 1
        assert str(table.get_row_at(0)[1]) == "P1"


@pytest.mark.asyncio
async def test_tui_dashboard_screen():
    """Test the DashboardScreen opening and period switching."""
    app = WtlApp()
    async with app.run_test(size=(120, 60)) as pilot:
        await pilot.press("d")
        await pilot.pause()

        from work_time_logger.dashboard import DashboardScreen

        assert isinstance(app.screen, DashboardScreen)

        await pilot.press("m")
        assert app.screen.period == "month"

        await pilot.press("w")
        assert app.screen.period == "week"

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, DashboardScreen)


@pytest.mark.asyncio
async def test_tui_arrow_key_adjustment():
    """Test arrow key value adjustment in OverlayInput for Date, Time, and Duration."""
    operations.create_empty_log()
    app = WtlApp()
    async with app.run_test(size=(120, 60)) as pilot:
        table = app.query_one(DataTable)
        app.set_focus(table)

        # 1. Test Date (col 3)
        table.move_cursor(row=0, column=3)
        await pilot.press("enter")
        await pilot.pause(0.1)
        overlay = app.query_one("#edit-overlay")
        assert overlay.edit_mode == "date_only"
        old_val = overlay.value
        await pilot.press("up")
        assert overlay.value != old_val
        await pilot.press("escape")

        # 2. Test Start Time (col 4)
        table.move_cursor(row=0, column=4)
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert overlay.edit_mode == "time_only"
        # Since it's formatted as HH:mm:ss, but the original empty log
        # might have "" or full ISO
        # Empty log has start_time set to current time
        # in operations.create_empty_log()
        assert len(overlay.value) == 5  # HH:mm
        await pilot.press("escape")

        # 3. Test Duration (col 6)
        table.move_cursor(row=0, column=6)
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert overlay.edit_mode == "duration"
        overlay.value = "1.0"
        await pilot.press("up")
        # Default step is now 0.1 (as set in tests or by default)
        assert overlay.value == "1.1"
        await pilot.press("down")
        assert overlay.value == "1.0"
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_tui_misc_actions():
    """Test various global actions and focus switching."""
    operations.add_project("MockProj")
    operations.add_job("MockJob", "MockProj")
    operations.start_log("MockProj", "MockJob")
    operations.stop_all_logs()
    app = WtlApp()
    async with app.run_test(size=(120, 60)) as pilot:
        # action_switch_focus
        assert app.focused == app.logs_table
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused == app.projects_tree

        # action_start_unassigned
        await pilot.press("S")
        await pilot.pause()

        # Check that it started an unassigned log
        # (row counts should increase or be updated)
        assert app.logs_table.row_count > 0

        # action_show_summary
        await pilot.press("v")
        await pilot.pause()
        from work_time_logger.daily_summary import DailySummaryScreen

        assert isinstance(app.screen, DailySummaryScreen)
        await pilot.press("escape")
        await pilot.pause()

        # action_export_logs (just open and close)
        await pilot.press("e")
        await pilot.pause()
        from work_time_logger.modals import ExportLogsModal

        assert isinstance(app.screen, ExportLogsModal)
        await pilot.press("escape")
        await pilot.pause()

        # action_add_project (p)
        await pilot.press("p")
        await pilot.pause()
        await pilot.press("escape")

        # action_add_job (j)
        await pilot.press("j")
        await pilot.pause()
        await pilot.press("escape")

        # action_add_log (a)
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("escape")

        # action_delete_log (d)
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("escape")

        # action_delete_job (shift+d / D)
        await pilot.press("D")
        await pilot.pause()
        await pilot.press("escape")

        # action_delete_project (ctrl+d)
        await pilot.press("ctrl+d")
        await pilot.pause()
        await pilot.press("escape")

        # action_log_assign (shift+a / A)
        await pilot.press("A")
        await pilot.pause()
        await pilot.press("escape")

        # action_filter (f)
        await pilot.press("f")
        await pilot.pause()
        await pilot.press("escape")

        # action_clear_filter (c)
        await pilot.press("c")
        await pilot.pause()

        # action_help (?)
        await pilot.press("?")
        await pilot.pause()
        await pilot.press("escape")

        # action_dashboard (b)
        await pilot.press("b")
        await pilot.pause()
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_tui_smart_input_date_time():
    """Test smart date and time input parsing in cell edits."""
    operations.create_empty_log()
    app = WtlApp()
    async with app.run_test(size=(120, 60)) as pilot:
        table = app.query_one(DataTable)
        app.set_focus(table)

        # 1. Edit Date (col 3) with smart format
        table.move_cursor(row=0, column=3)
        await pilot.press("enter")
        await pilot.pause(0.1)
        for char in "+1":
            await pilot.press(char)
        await pilot.press("enter")
        await pilot.pause(0.1)

        # 2. Edit Date with invalid format to trigger error
        table.move_cursor(row=0, column=3)
        await pilot.press("enter")
        await pilot.pause(0.1)
        for char in "inv":
            await pilot.press(char)
        await pilot.press("enter")
        await pilot.pause(0.1)
        # Should stay on table, notification shown

        # 3. Edit Start Time (col 4) with smart format "18"
        table.move_cursor(row=0, column=4)
        await pilot.press("enter")
        await pilot.pause(0.1)
        # clear input
        await pilot.press("backspace")
        await pilot.press("backspace")
        await pilot.press("backspace")
        await pilot.press("backspace")
        await pilot.press("backspace")
        for char in "18":
            await pilot.press(char)
        await pilot.press("enter")
        await pilot.pause(0.1)

        # 4. Edit with start > end time error
        table.move_cursor(row=0, column=5)  # End Time
        await pilot.press("enter")
        await pilot.pause(0.1)
        # clear input
        await pilot.press("backspace")
        await pilot.press("backspace")
        await pilot.press("backspace")
        await pilot.press("backspace")
        await pilot.press("backspace")
        for char in "10":  # 10:00 (which is before 18:00 start)
            await pilot.press(char)
        await pilot.press("enter")
        await pilot.pause(0.1)


@pytest.mark.asyncio
async def test_tui_start_while_running():
    """Test trying to start a job from the tree or via hotkey when one is running."""
    operations.add_project("MockProj")
    operations.add_job("MockJob", "MockProj")
    operations.start_log("MockProj", "MockJob")

    app = WtlApp()
    async with app.run_test(size=(120, 60)) as pilot:
        # pressing 's' should fail because a job is already running
        await pilot.press("s")
        await pilot.pause()

        # Try tree node enter
        app.set_focus(app.projects_tree)
        # Root is expanded by default (for new project).
        # Down once to MockProj, Down twice to MockJob
        await pilot.press("down")
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        # Nothing should crash; notification handles it
        assert app.logs_table.row_count > 0


@pytest.mark.asyncio
async def test_tui_restart_job():
    """Test restarting (cloning) a job from a selected log entry via 'r'."""
    operations.add_project("RestartProj")
    operations.add_job("RestartJob", "RestartProj")
    operations.start_log("RestartProj", "RestartJob")
    operations.stop_all_logs()  # Complete it

    app = WtlApp()
    async with app.run_test(size=(120, 60)) as pilot:
        table = app.query_one(DataTable)
        app.set_focus(table)
        table.move_cursor(row=0, column=0)

        # Row 0 is the one we just stopped.
        # Press 'r' to restart
        await pilot.press("r")
        await pilot.pause(0.1)

        # Now there should be 2 rows (the old one and the new one)
        assert table.row_count == 2

        # The new one should be at the top (row 0) as logs are sorted DESC
        new_row = table.get_row_at(0)
        assert str(new_row[1]) == "RestartProj"
        assert str(new_row[2]) == "RestartJob"
        assert "Running..." in str(new_row[5])  # End Time column
