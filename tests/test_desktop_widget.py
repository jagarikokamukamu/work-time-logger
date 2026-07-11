"""Tests for the desktop widget package."""

from unittest.mock import MagicMock, patch

import pytest
import typer

from work_time_logger.widget.controller import TaskController


def test_widget_cli_command_missing_dependency():
    """Test that the wtl widget command exits gracefully if flet is not installed."""
    import builtins

    from work_time_logger.cli import widget

    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "flet" or name == "work_time_logger.widget":
            # widget 自身、あるいは flet のロード時に ImportError をシミュレート
            raise ImportError("flet module not found")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        with pytest.raises(typer.Exit) as exc_info:
            widget()
        assert exc_info.value.exit_code == 1


@patch("asyncio.create_subprocess_exec")
def test_controller_monitoring_loop_executes_wtl(mock_exec):
    """Test that _monitoring_loop executes status watch and parses output."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    mock_process = AsyncMock()
    mock_process.terminate = MagicMock()
    mock_process.stdout = AsyncMock()
    mock_process.stdout.readline.side_effect = [
        (
            b'[{"project_name": "Proj", "job_name": "Job", '
            b'"start_time": "2026-07-05T03:00:00"}]\n'
        ),
        b"",
    ]
    mock_exec.return_value = mock_process

    class FakePage:
        def update(self):
            pass

    class FakeUI:
        def __init__(self):
            self.states = []

        def update_state(self, **kwargs):
            self.states.append(kwargs)

        def update(self):
            pass

    controller = TaskController()
    controller.is_monitoring = True

    ui = FakeUI()
    asyncio.run(controller._monitoring_loop(FakePage(), ui))

    from unittest.mock import ANY

    mock_exec.assert_any_call(
        "wtl",
        "status",
        "--watch",
        "--json",
        stdout=asyncio.subprocess.PIPE,
        stderr=ANY,
        env=ANY,
    )
    assert len(ui.states) > 0
    assert ui.states[0]["is_running"] is True
    assert "Proj / Job" in ui.states[0]["job_name"]


def test_widget_ui_initialization():
    """Verify the widget UI and controllers initialize without errors."""
    try:
        import flet as ft
    except ImportError:
        pytest.skip("flet library is not installed, skipping UI initialization test.")

    from work_time_logger.widget.app import main

    mock_page = MagicMock(spec=ft.Page)
    mock_page.window = MagicMock()
    mock_page.controls = []

    def mock_add(*controls):
        mock_page.controls.extend(controls)

    mock_page.add = mock_add

    # UIのプロパティ設定とウィジェット追加処理がクラッシュせず成功することを確認
    import asyncio

    asyncio.run(main(mock_page))

    assert mock_page.title == "WTL Desktop Widget"
    assert mock_page.window.always_on_top is True
    assert mock_page.window.frameless is True
    assert mock_page.window.bgcolor == ft.Colors.TRANSPARENT
    assert mock_page.window.width == 300
    assert mock_page.window.height == 70

    assert len(mock_page.controls) > 0
    assert isinstance(mock_page.controls[0], ft.WindowDragArea)


def test_widget_close_via_button():
    """Verify the close button stops monitoring and destroys the window."""
    try:
        import flet as ft
    except ImportError:
        pytest.skip("flet library is not installed, skipping close button test.")

    from work_time_logger.widget.app import main

    mock_page = MagicMock(spec=ft.Page)
    mock_page.window = MagicMock()
    mock_page.controls = []

    def mock_add(*controls):
        mock_page.controls.extend(controls)

    mock_page.add = mock_add

    import asyncio

    asyncio.run(main(mock_page))

    # Find the ActiveTaskContainer and trigger close
    drag_area = mock_page.controls[0]
    container = drag_area.content
    close_button = container.close_button
    assert close_button.on_click is not None

    close_button.on_click(MagicMock())

    # Assert window destroy is triggered via run_task
    mock_page.run_task.assert_any_call(mock_page.window.destroy)


def test_widget_close_via_keyboard():
    """Verify that pressing Escape or Q stops monitoring and destroys the window."""
    try:
        import flet as ft
    except ImportError:
        pytest.skip("flet library is not installed, skipping keyboard shortcut test.")

    from work_time_logger.widget.app import main

    mock_page = MagicMock(spec=ft.Page)
    mock_page.window = MagicMock()
    mock_page.controls = []

    def mock_add(*controls):
        mock_page.controls.extend(controls)

    mock_page.add = mock_add

    import asyncio

    asyncio.run(main(mock_page))

    # Verify keyboard event listener
    assert mock_page.on_keyboard_event is not None

    # Simulate Escape key
    mock_event = MagicMock()
    mock_event.key = "Escape"
    mock_page.on_keyboard_event(mock_event)
    mock_page.run_task.assert_any_call(mock_page.window.destroy)

    # Simulate Q key
    mock_page.run_task.reset_mock()
    mock_event.key = "q"
    mock_page.on_keyboard_event(mock_event)
    mock_page.run_task.assert_any_call(mock_page.window.destroy)


@patch("asyncio.create_subprocess_exec")
def test_controller_monitoring_loop_no_error_on_page_update(mock_exec):
    """Verify _monitoring_loop does NOT raise 'NoneType can't be awaited'
    when page.update() is synchronous (returns None)."""
    import asyncio
    import io
    from unittest.mock import AsyncMock, MagicMock

    # Mock process and its stdout
    mock_process = AsyncMock()
    mock_process.terminate = MagicMock()
    mock_process.stdout = AsyncMock()
    mock_process.stdout.readline = AsyncMock(return_value=b"[]\n")
    mock_exec.return_value = mock_process

    # Simulate the real Flet Page where page.update() is synchronous and returns None
    class FakePage:
        def update(self):
            return None  # synchronous, returns None - this is what real Flet does

    class FakeUI:
        def __init__(self):
            self.update_called = False

        def update_state(self, **kwargs):
            pass

        def update(self):
            controller.is_monitoring = False  # stop after first iteration

    controller = TaskController()
    controller.is_monitoring = True

    # Capture print output to detect "Error in monitoring loop" messages
    captured = io.StringIO()
    import sys

    old_stdout = sys.stdout
    sys.stdout = captured

    try:
        asyncio.run(controller._monitoring_loop(FakePage(), FakeUI()))
    finally:
        sys.stdout = old_stdout

    output = captured.getvalue()
    assert "Error in monitoring loop" not in output, (
        f"'NoneType can't be awaited' or other error detected:\n{output}"
    )


@patch("work_time_logger.cli.subprocess.Popen")
def test_widget_main_detach(mock_popen, tmp_path):
    """Test starting the widget with default detach (background) mode."""
    from typer.testing import CliRunner

    from work_time_logger import cli, db

    test_db_dir = tmp_path / ".wtl_test"
    test_db_dir.mkdir()
    db.DB_DIR = test_db_dir

    runner = CliRunner()
    result = runner.invoke(cli.app, ["widget"])
    assert result.exit_code == 0
    assert "Started desktop widget in background." in result.stdout
    mock_popen.assert_called_once()


@patch("work_time_logger.widget.run_widget")
def test_widget_main_wait(mock_run_widget, tmp_path):
    """Test starting the widget with --wait option (foreground)."""
    from typer.testing import CliRunner

    from work_time_logger import cli, db

    test_db_dir = tmp_path / ".wtl_test"
    test_db_dir.mkdir()
    db.DB_DIR = test_db_dir

    runner = CliRunner()
    result = runner.invoke(cli.app, ["widget", "--wait"])
    assert result.exit_code == 0
    mock_run_widget.assert_called_once()
