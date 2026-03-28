"""Unit tests for the custom widgets in work_time_logger.widgets."""

from datetime import datetime
from pathlib import Path

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input

from work_time_logger import db, operations
from work_time_logger.widgets import (
    ConfirmDeleteModal,
    CopyableDataTable,
    DailySummaryModal,
    ExportLogsModal,
    FilterModal,
    HelpModal,
    JobCodeModal,
    OverlayInput,
)


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


class DummyApp(App):
    """A dummy Textual App for testing widgets."""

    def compose(self) -> ComposeResult:
        # Provide some initial widgets to mount others onto or over
        yield CopyableDataTable(id="table")
        yield OverlayInput(id="overlay")


@pytest.mark.asyncio
async def test_copyable_data_table(monkeypatch):
    """Test the CopyableDataTable clipboard copy functionally."""
    app = DummyApp()
    async with app.run_test(size=(120, 60)) as pilot:
        table = app.query_one(CopyableDataTable)
        table.add_columns("A", "B")
        table.add_row("1", "2")
        table.focus()

        # Mock app.copy_to_clipboard
        copied_text = None

        def mock_copy(text):
            nonlocal copied_text
            copied_text = text

        monkeypatch.setattr(app, "copy_to_clipboard", mock_copy)

        # Move cursor to cell (0, 0)
        table.move_cursor(row=0, column=0)

        # Trigger copy action
        await pilot.press("c")
        from asyncio import sleep

        await sleep(0.1)

        assert copied_text == "1"


@pytest.mark.asyncio
async def test_help_modal():
    """Test HelpModal display and dismissal."""
    app = DummyApp()
    async with app.run_test(size=(120, 60)) as pilot:
        await app.push_screen(HelpModal())
        assert isinstance(app.screen, HelpModal)

        # Dismiss modal
        await pilot.press("escape")
        from asyncio import sleep

        await sleep(0.1)
        assert not isinstance(app.screen, HelpModal)


@pytest.mark.asyncio
async def test_confirm_delete_modal():
    """Test ConfirmDeleteModal actions."""
    app = DummyApp()
    async with app.run_test(size=(120, 60)) as pilot:
        modal = ConfirmDeleteModal()
        # Mock dismiss to check return value
        result = None
        def mock_dismiss(res):
            nonlocal result
            result = res
            
        modal.dismiss = mock_dismiss
        
        await app.push_screen(modal)
        
        # Test 'yes' action directly
        modal.action_yes()
        assert result is True
        
        # Test 'no' action directly
        modal.action_no()
        assert result is False


@pytest.mark.asyncio
async def test_filter_modal():
    """Test FilterModal."""
    app = DummyApp()
    async with app.run_test(size=(120, 60)) as pilot:
        modal = FilterModal({"project": "ProjA"})
        
        result = None
        def mock_dismiss(res):
            nonlocal result
            result = res
            
        modal.dismiss = mock_dismiss
        await app.push_screen(modal)
        
        # Check initial value
        proj_input = modal.query_one("#f-project", Input)
        assert proj_input.value == "ProjA"
        
        # Simulate Clear button
        await pilot.click("#btn-clear")
        await pilot.pause()
        assert result == {"project": None, "job": None, "start": None, "end": None}


@pytest.mark.asyncio
async def test_export_logs_modal():
    """Test ExportLogsModal."""
    app = DummyApp()
    async with app.run_test() as pilot:
        modal = ExportLogsModal()
        
        result = None
        def mock_dismiss(res):
            nonlocal result
            result = res
            
        modal.dismiss = mock_dismiss
        await app.push_screen(modal)
        
        # Simulate cancel
        await pilot.click("#btn-cancel")
        await pilot.pause()
        assert result is None
        
        # Simulate Export
        await pilot.click("#btn-export")
        await pilot.pause()
        assert result is not None
        assert len(result) == 3


@pytest.mark.asyncio
async def test_overlay_input():
    """Test OverlayInput standalone adjustment without full TUI."""
    app = DummyApp()
    async with app.run_test() as pilot:
        overlay = app.query_one(OverlayInput)
        
        # Test duration mode increment
        overlay.edit_mode = "duration"
        overlay.value = "1.0"
        overlay.action_increment()
        assert overlay.value == "1.1"
        
        overlay.action_decrement()
        assert overlay.value == "1.0"

        # Test cancel action
        # It hides itself on cancel
        overlay.action_cancel()
        assert overlay.styles.display == "none"

