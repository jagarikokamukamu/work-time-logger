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


@patch("work_time_logger.widget.controller.subprocess.run")
def test_controller_run_wtl_command_success(mock_run):
    """Test that _run_wtl_command successfully runs and returns stdout."""
    mock_res = MagicMock()
    mock_res.stdout = "Running: ProjectA / JobB\n"
    mock_run.return_value = mock_res

    controller = TaskController()
    stdout = controller._run_wtl_command(["status"])
    assert stdout == "Running: ProjectA / JobB"
    mock_run.assert_called_with(
        ["wtl", "status"], capture_output=True, text=True, check=True
    )


@patch("work_time_logger.widget.controller.subprocess.run")
def test_controller_run_wtl_command_fallback(mock_run):
    """Test that _run_wtl_command falls back to sys.executable when 'wtl' fails."""
    import sys

    mock_res = MagicMock()
    mock_res.stdout = "Running fallback\n"
    mock_run.side_effect = [FileNotFoundError("wtl not found"), mock_res]

    controller = TaskController()
    stdout = controller._run_wtl_command(["status"])
    assert stdout == "Running fallback"
    assert mock_run.call_count == 2

    # Verify fallback call args
    fallback_args = mock_run.call_args_list[1][0][0]
    assert fallback_args[0] == sys.executable
    assert "work_time_logger.cli" in fallback_args[2]


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


def test_controller_monitoring_loop_no_error_on_page_update():
    """Verify _monitoring_loop does NOT raise 'NoneType can\'t be awaited'
    when page.update() is synchronous (returns None)."""
    import asyncio
    import io

    from work_time_logger.widget.controller import TaskController

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
    controller._run_wtl_command = lambda args: "[]"

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
