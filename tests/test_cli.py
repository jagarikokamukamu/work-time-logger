import pytest
from typer.testing import CliRunner

from work_time_logger import cli, db

runner = CliRunner()


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    """Override the database path to use a temporary directory for tests"""
    test_db_dir = tmp_path / ".wtl_test"
    test_db_dir.mkdir()
    db.DB_DIR = test_db_dir
    db.DB_PATH = test_db_dir / "test_db.sqlite3"
    db.init_db()
    yield


def test_project_add_and_list():
    result = runner.invoke(cli.app, ["project", "add", "-n", "Test Project CLI"])
    assert result.exit_code == 0
    assert "Added project 'Test Project CLI'" in result.stdout

    result2 = runner.invoke(cli.app, ["project", "list"])
    assert result2.exit_code == 0
    assert "Test Project CLI" in result2.stdout


def test_start_unassigned_from_cli():
    # Ensure starting unassigned works
    result = runner.invoke(cli.app, ["start", "--unassigned"])
    assert result.exit_code == 0
    assert "Started tracking an unassigned job" in result.stdout

    # List logs to check if it's there
    result = runner.invoke(cli.app, ["log", "list"])
    assert result.exit_code == 0
    assert "[Unassigned]" in result.stdout
    assert "Running..." in result.stdout

    # Stop it
    result = runner.invoke(cli.app, ["stop"])
    assert result.exit_code == 0
    assert "Stopped current job tracking" in result.stdout


def test_start_fail_without_unassigned_flag():
    # If no project/job is provided and --unassigned is NOT passed, it should fail
    result = runner.invoke(cli.app, ["start"])
    assert result.exit_code == 1
    assert "You must provide a project and job name" in result.stdout
