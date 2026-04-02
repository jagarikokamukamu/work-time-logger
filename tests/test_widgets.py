import asyncio
import textwrap
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
    db.DB_PATH = test_db_dir / "test_db.sqlite3"

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
    async with app.run_test(size=(120, 60)) as _:
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
    async with app.run_test() as _:
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


@pytest.mark.asyncio
async def test_overlay_input_extended():
    """Test OverlayInput in date and time modes."""
    app = DummyApp()
    async with app.run_test() as _:
        overlay = app.query_one(OverlayInput)

        # Test date mode
        overlay.edit_mode = "date"
        overlay.value = "2023-10-01"
        overlay.action_increment()
        assert overlay.value != "2023-10-01"
        overlay.action_decrement()
        # verify it runs without crashing

        # Invalid date fallback
        overlay.value = "invalid"
        overlay.action_increment()
        # Should not crash, validation might leave it as invalid or reset

        # Test time mode
        overlay.edit_mode = "time"
        overlay.value = "10:00:00"
        # Increment/decrement should not crash
        overlay.action_increment()
        overlay.action_decrement()

        # Invalid time fallback
        overlay.value = "invalid"
        overlay.action_increment()

        # Test submit
        result = None

        def mock_callback(val):
            nonlocal result
            result = val

        overlay.callback = mock_callback
        await overlay.action_submit()
        # Just verifying it runs without crashing, and callback might be called.
        assert result == "invalid" or result is None


@pytest.mark.asyncio
async def test_job_code_modal_missing_job():
    """Test JobCodeModal when the specified job does not exist."""
    app = DummyApp()
    async with app.run_test() as pilot:
        operations.add_project("PJ1")
        # Do not add job

        modal = JobCodeModal("PJ1", "MissingJob")
        await app.push_screen(modal)

        table = modal.query_one(CopyableDataTable)
        # It should add an 'Error' row indicating job not found
        rows = [table.get_row_at(i) for i in range(table.row_count)]
        assert any("Error" in str(row) or "Job not found" in str(row) for row in rows)

        await pilot.click("#btn-close")


@pytest.mark.asyncio
async def test_daily_summary_modal_error(monkeypatch):
    """Test DailySummaryModal when exporter raises an exception."""
    app = DummyApp()
    async with app.run_test() as pilot:
        # Mock exporter to fail
        import work_time_logger.exporter as t_exp

        def mock_aggregate(*args, **kwargs):
            raise ValueError("Test Aggregation Error")

        monkeypatch.setattr(t_exp, "aggregate_logs", mock_aggregate)

        modal = DailySummaryModal()
        await app.push_screen(modal)

        table = modal.query_one(CopyableDataTable)
        rows = [table.get_row_at(i) for i in range(table.row_count)]
        assert any("Test Aggregation Error" in str(row) for row in rows)

        await pilot.press("escape")


@pytest.mark.asyncio
async def test_job_code_modal_editing_logic(tmp_path: Path):
    """Test the JobCodeModal editing logic following established patterns."""
    # Pattern: Use textwrap.dedent for profile setup in tests
    profile_path = db.DB_DIR / "profile.toml"
    profile_path.write_text(
        textwrap.dedent("""
        [export.extract]
        job_code = "^JC-(?P<kind>[A-Z])-(?P<num>\\\\d+)$"

        [import.mapping]
        description = "Fixed Desc"
        job_code = "JC-{{ kind }}-{{ num }}"
    """),
        encoding="utf-8",
    )

    # Setup test data
    operations.add_project("ProjE")
    # Description matches mapping to avoid 'AssertionError' conflict
    operations.add_job("JobE1", "ProjE", "Fixed Desc", "JC-K-123")

    app = DummyApp()
    async with app.run_test(size=(120, 60)) as pilot:
        modal = JobCodeModal("ProjE", "JobE1")
        await app.push_screen(modal)
        await pilot.pause()

        # Switch to import mode
        await pilot.press("t")
        await pilot.pause()

        # Verify initial deconstruction
        assert str(modal.import_row.get("kind")) == "K"
        assert str(modal.import_row.get("num")) == "123"

        # Simulate submission for DB update logic verification
        inp = modal.query_one("#job-code-edit-input", Input)
        modal._editing_col_name = "num"
        modal.on_edit_submitted(Input.Submitted(inp, "456"))

        await asyncio.sleep(0.5)

        # Integrity Check
        jobs = operations.list_jobs("ProjE")
        job = next((j for j in jobs if j["name"] == "JobE1"), None)
        assert job is not None
        assert job["code"] == "JC-K-456"
        assert job["description"] == "Fixed Desc"


@pytest.mark.asyncio
async def test_daily_summary_date_jump():
    """Test the date jump feature in DailySummaryModal."""
    app = DummyApp()
    async with app.run_test(size=(120, 60)) as pilot:
        modal = DailySummaryModal()
        await app.push_screen(modal)
        await pilot.pause()

        # Initial date check
        from datetime import date
        today_str = date.today().isoformat()
        assert modal.target_date == today_str

        # Press '/' to show input
        await pilot.press("/")
        inp = modal.query_one("#date-input-overlay", Input)
        assert inp.styles.display == "block"
        assert inp.has_focus

        # Input a new date and submit
        await pilot.press(*"2025-01-01")
        await pilot.press("enter")
        await pilot.pause()

        # Check if date updated and input hidden
        assert modal.target_date == "2025-01-01"
        assert inp.styles.display == "none"

        # Test escape to cancel
        await pilot.press("/")
        assert inp.styles.display == "block"
        await pilot.press("escape")
        assert inp.styles.display == "none"


@pytest.mark.asyncio
async def test_daily_summary_color_coding():
    """Test the color coding in DailySummaryModal."""
    # Setup test data
    target_date = "2023-10-01"
    operations.add_project("ProjColor")
    operations.add_job("Job1", "ProjColor", code="JC-1")
    operations.add_job("Job2", "ProjColor", code="JC-2")

    # Add logs
    l1 = operations.start_log("ProjColor", "Job1")
    operations.update_log(
        l1,
        start_time=f"{target_date}T10:00:00",
        end_time=f"{target_date}T11:00:00"
    )

    # stop_log() would stop l1 if it was running, but we already updated it.
    # We need to make sure no job is running before starting another.
    l2 = operations.start_log("ProjColor", "Job2")
    operations.update_log(
        l2,
        start_time=f"{target_date}T12:00:00",
        end_time=f"{target_date}T13:00:00"
    )

    app = DummyApp()
    async with app.run_test(size=(120, 60)) as pilot:
        modal = DailySummaryModal()
        modal.target_date = target_date
        await app.push_screen(modal)
        await pilot.pause()

        table = modal.query_one(CopyableDataTable)
        # Check first column is the colored dot
        # Note: table.columns is a dict-like object
        cols = list(table.columns.values())
        assert "●" in str(cols[0].label)

        # Check rows have colors
        # aggregated_results are sorted, so Job1/Job2 order should be consistent
        row0 = table.get_row_at(0)
        row1 = table.get_row_at(1)

        # row[0] is the rich.Text "●"
        assert "●" in str(row0[0])
        assert "●" in str(row1[0])

        # Verify visualizer intervals have colors matching the rows
        from work_time_logger.widgets import TimelineVisualizer
        viz = modal.query_one(TimelineVisualizer)
        assert len(viz.intervals) == 2
        # interval: (start, end, color)
        # By default, they should have different colors because group_by=['job_name']
        # (if default profile is used)
        assert viz.intervals[0][2] != ""
        assert viz.intervals[1][2] != ""
