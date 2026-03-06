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
    async with app.run_test(size=(120, 60)) as pilot:
        tree = app.query_one(Tree)
        table = app.query_one(DataTable)

        # Check tree
        assert len(tree.root.children) == 1
        assert str(tree.root.children[0].label) == "Test Project"

        # Check table
        assert table.row_count == 1
        row = table.get_row_at(0)
        assert len(row) == 6
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
async def test_tui_edit_log_modal():
    """Test editing an existing log via LogEditModal."""
    # Add prerequisites to avoid ValueError on missing project/job
    operations.add_project("NewProj")
    operations.add_job("NewJob", "NewProj")
    operations.create_empty_log()

    app = WtlApp()
    async with app.run_test(size=(120, 60)) as pilot:
        table = app.query_one(DataTable)
        app.set_focus(table)

        # Assuming the newly created empty log is at the top/first selection
        await pilot.press("enter")
        await pilot.pause()

        # Modal should be open
        assert len(app.screen_stack) > 1

        await pilot.click("#p_name")
        await pilot.press("backspace", "backspace", "backspace", "backspace")
        for char in "NewProj":
            await pilot.press(char)

        await pilot.click("#j_name")
        await pilot.press("backspace", "backspace", "backspace", "backspace")
        for char in "NewJob":
            await pilot.press(char)

        await pilot.click("#memo")
        for char in "TestMemo":
            await pilot.press(char)

        await pilot.click("#save")
        await pilot.pause()

        # Modal should be closed
        assert len(app.screen_stack) == 1

        logs = operations.list_logs()
        assert logs[0]["project_name"] == "NewProj"
        assert logs[0]["job_name"] == "NewJob"
        assert logs[0]["memo"] == "TestMemo"
