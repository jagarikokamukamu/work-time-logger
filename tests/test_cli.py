import pytest
from typer.testing import CliRunner

from work_time_logger import cli, db, operations

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
    result = runner.invoke(cli.app, ["project", "add", "-p", "Test Project CLI"])
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
    assert "[Unassigne" in result.stdout
    assert "Running..." in result.stdout

    # Stop it
    result = runner.invoke(cli.app, ["stop"])
    assert result.exit_code == 0
    assert "Stopped current job tracking" in result.stdout


def test_start_with_options():
    # Setup
    runner.invoke(cli.app, ["project", "add", "-p", "Start Proj"])
    runner.invoke(cli.app, ["job", "add", "-j", "Start Job", "-p", "Start Proj"])

    # Start with options
    result = runner.invoke(cli.app, ["start", "-p", "Start Proj", "-j", "Start Job"])
    assert result.exit_code == 0
    assert "Started tracking 'Start Job' in 'Start Proj'" in result.stdout

    # Stop it
    runner.invoke(cli.app, ["stop"])


def test_start_fail_without_unassigned_flag():
    # If no project/job is provided and --unassigned is NOT passed, it should fail
    result = runner.invoke(cli.app, ["start"])
    assert result.exit_code == 1
    assert "You must provide a project and job name" in result.stdout


def test_job_import(tmp_path):
    runner.invoke(cli.app, ["project", "add", "-p", "Import Project"])
    csv_file = tmp_path / "jobs.csv"
    csv_file.write_text("name,description\nJob1,Desc1\nJob2,Desc2")

    # Use a minimal profile so the user's profile.toml
    # mapping doesn't interfere
    profile_file = tmp_path / "profile.toml"
    profile_file.write_text(
        '[import.mapping]\nname = "{{ name }}"\ndescription = "{{ description }}"\n'
    )

    result = runner.invoke(
        cli.app,
        [
            "job",
            "import",
            str(csv_file),
            "-p",
            "Import Project",
            "-r",
            str(profile_file),
        ],
    )
    assert result.exit_code == 0
    assert "Imported 2 jobs" in result.stdout

    result2 = runner.invoke(cli.app, ["job", "list", "--project", "Import Project"])
    assert "Job1" in result2.stdout
    assert "Job2" in result2.stdout


def test_log_delete():
    # Make a manual log
    runner.invoke(cli.app, ["start", "--unassigned"])
    runner.invoke(cli.app, ["stop"])

    # Use the id of the first log returned
    logs = operations.list_logs()
    log_id = str(logs[0]["id"])

    result = runner.invoke(cli.app, ["log", "delete", log_id])
    assert result.exit_code == 0
    assert f"Deleted log {log_id}" in result.stdout


def test_log_assign():
    # Setup
    runner.invoke(cli.app, ["project", "add", "-p", "Proj A"])
    runner.invoke(cli.app, ["job", "add", "-j", "Job A", "-p", "Proj A"])
    runner.invoke(cli.app, ["start", "--unassigned"])
    runner.invoke(cli.app, ["stop"])

    logs = operations.list_logs()
    log_id = str(logs[0]["id"])

    result = runner.invoke(
        cli.app, ["log", "assign", log_id, "-p", "Proj A", "-j", "Job A"]
    )
    assert result.exit_code == 0
    assert (
        f"Assigned log ID {log_id}" in result.stdout
        or f"assigned Log ID {log_id}" in result.stdout
    )


def test_job_delete():
    runner.invoke(cli.app, ["project", "add", "-p", "Del Proj"])
    runner.invoke(cli.app, ["job", "add", "-j", "Del Job", "-p", "Del Proj"])
    result = runner.invoke(
        cli.app, ["job", "delete", "-j", "Del Job", "-p", "Del Proj"]
    )
    assert result.exit_code == 0
    assert "Deleted job" in result.stdout
