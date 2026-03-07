"""Unit tests for the Textual TUI using pytest and textual.testing."""

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
        assert len(row) == 7
        assert row[1] == "Test Project"
        assert row[2] == "Test Job"


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
        await pilot.pause(0.1)  # wait for overlay mount/focus

        # Overlay input should be visible and focused
        overlay = app.query_one("#edit-overlay")
        assert overlay.styles.display == "block"
        assert app.focused == overlay

        # Set value simulation
        overlay.value = "2026-12-31 12:00:00"

        await pilot.press("enter")
        await pilot.pause(0.1)

        # Overlay should be closed
        assert overlay.styles.display == "none"
        assert app.focused == table

        logs = operations.list_logs()
        assert logs[0]["start_time"] == "2026-12-31T12:00:00"


@pytest.mark.asyncio
async def test_tui_job_selection_modal():
    """Test the JobSelectionModal behavior (opening, searching, closing)."""
    operations.add_project("SearchProj")
    operations.add_job("SearchJob1", "SearchProj")
    operations.add_job("SearchJob2", "SearchProj")

    app = WtlApp()
    async with app.run_test(size=(120, 60)) as pilot:
        await pilot.press("s")
        await pilot.pause()

        # Check if modal is active
        from work_time_logger.widgets import JobSelectionModal
        assert isinstance(app.screen, JobSelectionModal)

        # Type to search
        await pilot.press("S", "e", "a", "r", "c", "h", "J", "o", "b", "2")
        await pilot.pause()

        # Press tab to focus OptionList, down to highlight first item, then enter to select
        await pilot.press("tab")
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        # Modal should be dismissed, job tracking should start
        assert not isinstance(app.screen, JobSelectionModal)
        logs = operations.list_logs()
        assert len(logs) == 1
        assert logs[0]["job_name"] == "SearchJob2"


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
        assert len(operations.list_logs()) == 1  # Not deleted

        # Trigger again and confirm
        await pilot.press("D")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        
        # We need to test the action completes
        assert len(operations.list_logs()) == 0


@pytest.mark.asyncio
async def test_tui_overlay_keys():
    """Test keys like Up/Down, Esc, Tab on OverlayInput."""
    operations.create_empty_log()
    app = WtlApp()
    async with app.run_test(size=(120, 60)) as pilot:
        table = app.query_one(DataTable)
        app.set_focus(table)
        
        # Test ESC for Memo column
        table.move_cursor(row=0, column=6) # Memo
        await pilot.press("enter")
        await pilot.pause(0.1)
        
        overlay = app.query_one("#edit-overlay")
        assert app.focused == overlay
        
        # ESC cancels
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert app.focused == table
        
        # Test UP/DOWN on Date
        table.move_cursor(row=0, column=4) # Start Time
        await pilot.press("enter")
        await pilot.pause(0.1)
        
        assert overlay.edit_mode == "date"
        # Since cursor starts at end or front, let's just press down and see if it decreases year or second
        # depending on cursor pos (Textual's Input cursor starts at end if value is set).
        # We just want to ensure it doesn't crash:
        await pilot.press("up")
        await pilot.press("down")
        
        # Cancel with tab
        await pilot.press("tab")
        await pilot.pause(0.1)
        assert app.focused == table

