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
    operations.stop_log()

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
        assert row[1] == "Test Project"
        assert row[2] == "Test Job"
        assert row[3] == datetime.now().strftime("%Y-%m-%d")


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
        assert row[1] == "[未割り当て]"
        assert row[2] == "[未割り当て]"


@pytest.mark.asyncio
async def test_tui_edit_log_cell():
    """Test editing an existing log's time via in-place overlay input."""
    operations.add_project("NewProj")
    operations.add_job("NewJob", "NewProj")
    operations.create_empty_log()

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

        # Set value simulation (now HH:mm:ss)
        overlay.value = "12:34:56"

        await pilot.press("enter")
        await pilot.pause(0.1)

        assert overlay.styles.display == "none"
        assert app.focused == table

        logs = operations.list_logs()
        # Today's date + T + 12:34:56
        today = datetime.now().strftime("%Y-%m-%d")
        assert logs[0]["start_time"] == f"{today}T12:34:56"


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

        from work_time_logger.widgets import ConfirmDeleteModal
        assert isinstance(app.screen, ConfirmDeleteModal)

        # Cancel with 'n'
        await pilot.press("n")
        await pilot.pause()
        assert not isinstance(app.screen, ConfirmDeleteModal)
        assert len(operations.list_logs()) == 1

        # Trigger again and confirm
        await pilot.press("D")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        
        assert len(operations.list_logs()) == 0


@pytest.mark.asyncio
async def test_tui_filtering():
    """Test the FilterModal and filtering logic."""
    operations.add_project("P1")
    operations.add_job("J1", "P1")
    operations.start_log("P1", "J1")
    operations.stop_log()
    
    operations.add_project("P2")
    operations.add_job("J2", "P2")
    operations.start_log("P2", "J2")
    operations.stop_log()
    
    app = WtlApp()
    async with app.run_test(size=(120, 60)) as pilot:
        table = app.query_one(DataTable)
        assert table.row_count == 2
        
        await pilot.press("f")
        await pilot.pause()
        
        from work_time_logger.widgets import FilterModal
        assert isinstance(app.screen, FilterModal)
        
        await pilot.click("#f-project")
        for char in "P1":
            await pilot.press(char)
        
        await pilot.click("#btn-apply")
        await pilot.pause()
        
        assert table.row_count == 1
        assert table.get_row_at(0)[1] == "P1"


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
        # Since it's formatted as HH:mm:ss, but the original empty log might have "" or full ISO
        # Empty log has start_time set to current time in operations.create_empty_log()
        assert len(overlay.value) == 8 # HH:mm:ss
        await pilot.press("escape")
        
        # 3. Test Duration (col 6)
        table.move_cursor(row=0, column=6)
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert overlay.edit_mode == "duration"
        overlay.value = "1.0"
        await pilot.press("up")
        assert overlay.value == "1.25"
        await pilot.press("down")
        assert overlay.value == "1.0"
        await pilot.press("escape")
