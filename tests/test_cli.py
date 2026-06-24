import typing

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
    assert "Stopped 1 running job(s)!" in result.stdout


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


def test_start_parallel_with_force_cli():
    # Setup
    runner.invoke(cli.app, ["project", "add", "-p", "P1"])
    runner.invoke(cli.app, ["job", "add", "-j", "J1", "-p", "P1"])
    runner.invoke(cli.app, ["job", "add", "-j", "J2", "-p", "P1"])

    # Start first job
    runner.invoke(cli.app, ["start", "-p", "P1", "-j", "J1"])

    # Start second job without force should fail
    result = runner.invoke(cli.app, ["start", "-p", "P1", "-j", "J2"])
    assert "Error: A job is already running" in result.stdout
    assert "Use --force or -f" in result.stdout

    # Start second job with force should succeed
    result = runner.invoke(cli.app, ["start", "-p", "P1", "-j", "J2", "--force"])
    assert result.exit_code == 0
    assert "Started tracking 'J2' in 'P1'" in result.stdout

    # Verify two are running
    logs = operations.list_logs()
    running = [log for log in logs if log["end_time"] is None]
    assert len(running) == 2


def test_stop_multiple_logs_cli():
    # Setup two running jobs
    runner.invoke(cli.app, ["start", "--unassigned"])
    runner.invoke(cli.app, ["start", "--unassigned", "-f"])

    # Stop all
    result = runner.invoke(cli.app, ["stop"])
    assert result.exit_code == 0
    assert "Stopped 2 running job(s)!" in result.stdout

    # Verify none are running
    logs = operations.list_logs()
    running = [log for log in logs if log["end_time"] is None]
    assert len(running) == 0


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


def test_project_delete():
    runner.invoke(cli.app, ["project", "add", "-p", "Proj To Delete"])
    projects = operations.list_projects()
    pid = next((p["id"] for p in projects if p["name"] == "Proj To Delete"), None)
    assert pid is not None

    result = runner.invoke(cli.app, ["project", "delete", str(pid)])
    assert result.exit_code == 0
    assert f"Deleted project ID {pid}" in result.stdout


def test_job_list_with_codes(tmp_path):
    runner.invoke(cli.app, ["project", "add", "-p", "Code Proj"])
    runner.invoke(
        cli.app, ["job", "add", "-j", "Code Job", "-p", "Code Proj", "-c", "JTC-123"]
    )

    profile_file = tmp_path / "profile.toml"
    profile_file.write_text(
        "[export.extract]\n"
        'job_code = "JTC-(?P<ticket>\\\\d+)"\n'
        "[export.columns]\n"
        'Ticket = "{{ ticket }}"\n'
    )

    result = runner.invoke(
        cli.app,
        ["job", "list", "--project", "Code Proj", "--codes", "-r", str(profile_file)],
    )
    assert result.exit_code == 0
    assert "Ticket" in result.stdout
    assert "123" in result.stdout


def test_log_export(tmp_path):
    runner.invoke(cli.app, ["project", "add", "-p", "Export Proj"])
    runner.invoke(cli.app, ["job", "add", "-j", "Export Job", "-p", "Export Proj"])
    runner.invoke(cli.app, ["start", "-p", "Export Proj", "-j", "Export Job"])
    runner.invoke(cli.app, ["stop"])

    profile_file = tmp_path / "profile.toml"
    profile_file.write_text('[export.columns]\nProject = "{{ project_name }}"\n')
    out_file = tmp_path / "out.csv"

    result = runner.invoke(
        cli.app,
        ["log", "export", "-r", str(profile_file), "-o", str(out_file), "-d", "all"],
    )
    assert result.exit_code == 0
    assert "Successfully exported" in result.stdout
    assert out_file.exists()
    content = out_file.read_text("utf-8")
    assert "Export Proj" in content


def test_profile_open(monkeypatch, tmp_path):
    # Mock subprocess.run / os.startfile so it doesn't actually open the editor
    opened_file = None

    def mock_startfile(filepath):
        nonlocal opened_file
        opened_file = filepath

    def mock_run(args, **kwargs):
        nonlocal opened_file
        opened_file = args[1] if len(args) > 1 else None

    import os

    if hasattr(os, "startfile"):
        monkeypatch.setattr(os, "startfile", mock_startfile)
    else:
        import subprocess

        monkeypatch.setattr(subprocess, "run", mock_run)

    result = runner.invoke(cli.app, ["profile", "open"])
    assert result.exit_code == 0
    assert "Opening " in result.stdout
    assert opened_file is not None


def test_complete_project_name():
    operations.add_project("Alpha")
    operations.add_project("Beta")
    results = list(cli.complete_project_name("Al"))
    assert "Alpha" in results
    assert "Beta" not in results


def test_complete_job_name():
    operations.add_project("ProjX")
    operations.add_job("Job1", "ProjX")
    operations.add_job("Job2", "ProjX")

    # Mock Typer Context
    class MockContext:
        params = {"project_name": "ProjX"}

    results = list(cli.complete_job_name(typing.cast(typing.Any, MockContext()), "Jo"))
    assert "Job1" in results
    assert "Job2" in results


def test_start_exception():
    # Try starting a non-existent job in a non-existent project
    result = runner.invoke(cli.app, ["start", "-p", "NotExist", "-j", "NoJob"])
    assert result.exit_code == 0
    assert "Error:" in result.stdout
    # Ensure no log was started
    logs = operations.list_logs()
    assert not any(log.get("end_time") is None for log in logs)


def test_stop_exception():
    # Attempt to stop when no active log exists
    result = runner.invoke(cli.app, ["stop"])
    assert result.exit_code == 0
    assert "Error: No running jobs found." in result.stdout


def test_project_add_duplicate():
    runner.invoke(cli.app, ["project", "add", "-p", "Duplicate Project"])
    initial_count = len(operations.list_projects())

    # Add again
    result = runner.invoke(cli.app, ["project", "add", "-p", "Duplicate Project"])
    assert result.exit_code == 0
    assert "Error:" in result.stdout

    # Check that count hasn't changed
    assert len(operations.list_projects()) == initial_count


def test_job_add_missing_project():
    result = runner.invoke(cli.app, ["job", "add", "-j", "AnyJob", "-p", "NoProject"])
    assert result.exit_code == 0
    assert "Error:" in result.stdout
    assert len(operations.list_jobs("NoProject")) == 0


def test_job_delete_missing():
    runner.invoke(cli.app, ["project", "add", "-p", "Target Proj"])
    result = runner.invoke(
        cli.app, ["job", "delete", "-j", "UnknownJob", "-p", "Target Proj"]
    )
    assert result.exit_code == 0
    assert "not found" in result.stdout


def test_job_import_file_not_found():
    runner.invoke(cli.app, ["project", "add", "-p", "Target Proj"])
    result = runner.invoke(
        cli.app, ["job", "import", "non_existent.csv", "-p", "Target Proj"]
    )
    assert result.exit_code == 0
    assert "Error:" in result.stdout
    assert len(operations.list_jobs("Target Proj")) == 0


def test_log_delete_missing():
    result = runner.invoke(cli.app, ["log", "delete", "99999"])
    assert result.exit_code == 0
    assert "Error:" in result.stdout


def test_log_assign_missing():
    runner.invoke(cli.app, ["project", "add", "-p", "A"])
    runner.invoke(cli.app, ["job", "add", "-j", "B", "-p", "A"])
    result = runner.invoke(cli.app, ["log", "assign", "99999", "-p", "A", "-j", "B"])
    assert result.exit_code == 0
    assert "Error:" in result.stdout


def test_job_list_codes_exception(tmp_path):
    runner.invoke(cli.app, ["project", "add", "-p", "Error Proj"])
    # Write invalid TOML to trigger profile load error
    profile_file = tmp_path / "invalid.toml"
    profile_file.write_text("[export\nmissing_bracket=true")

    result = runner.invoke(
        cli.app,
        ["job", "list", "--project", "Error Proj", "--codes", "-r", str(profile_file)],
    )
    assert result.exit_code == 0
    assert "Error expanding job codes:" in result.stdout


def test_log_export_no_matching_logs(tmp_path):
    profile_file = tmp_path / "profile.toml"
    profile_file.write_text('[export.columns]\nCol=""')
    out_file = tmp_path / "out.csv"

    # Exporting a future date where no logs exist
    result = runner.invoke(
        cli.app,
        [
            "log",
            "export",
            "-r",
            str(profile_file),
            "-o",
            str(out_file),
            "-d",
            "2100-01-01",
        ],
    )
    assert result.exit_code == 0
    assert "No logs matched" in result.stdout


def test_profile_open_missing(monkeypatch, tmp_path):
    # Mock exporter.load_profile to raise an exception
    import work_time_logger.exporter as t_exp

    def mock_load_profile(path):
        raise ValueError("Simulated profile error")

    monkeypatch.setattr(t_exp, "load_profile", mock_load_profile)

    result = runner.invoke(cli.app, ["profile", "open"])
    assert result.exit_code == 0
    assert "Error ensuring profile exists:" in result.stdout


def test_profile_edit(monkeypatch, tmp_path):
    opened_file = None

    def mock_startfile(filepath):
        nonlocal opened_file
        opened_file = filepath

    def mock_run(args, **kwargs):
        nonlocal opened_file
        opened_file = args[1] if len(args) > 1 else None

    import os

    if hasattr(os, "startfile"):
        monkeypatch.setattr(os, "startfile", mock_startfile)
    else:
        import subprocess

        monkeypatch.setattr(subprocess, "run", mock_run)

    result = runner.invoke(cli.app, ["profile", "edit"])
    assert result.exit_code == 0
    assert "Opening " in result.stdout
    assert opened_file is not None

    opened_file = None
    result = runner.invoke(cli.app, ["profile", "open"])
    assert result.exit_code == 0
    assert "Opening " in result.stdout
    assert opened_file is not None


def test_profile_path():
    result = runner.invoke(cli.app, ["profile", "path"])
    assert result.exit_code == 0
    expected_path = str(db.DB_DIR / "profile.toml")
    assert expected_path in result.stdout.strip()


def test_profile_list():
    result = runner.invoke(cli.app, ["profile", "list"])
    assert result.exit_code == 0
    assert "tui.copy_memo_on_restart = True" in result.stdout
    assert "tui.duration_step = 0.1" in result.stdout


def test_profile_get_and_set():
    # 既存のキーの get
    result = runner.invoke(cli.app, ["profile", "get", "tui.duration_step"])
    assert result.exit_code == 0
    assert "0.1" in result.stdout

    # キーの set (float)
    result = runner.invoke(cli.app, ["profile", "set", "tui.duration_step", "0.5"])
    assert result.exit_code == 0
    assert "Successfully set 'tui.duration_step' to '0.5'" in result.stdout

    # 更新後の get
    result = runner.invoke(cli.app, ["profile", "get", "tui.duration_step"])
    assert result.exit_code == 0
    assert "0.5" in result.stdout

    # キーの set (bool)
    result = runner.invoke(cli.app, ["profile", "set", "tui.copy_memo_on_restart", "false"])
    assert result.exit_code == 0
    result = runner.invoke(cli.app, ["profile", "get", "tui.copy_memo_on_restart"])
    assert result.exit_code == 0
    assert "False" in result.stdout

    # キーの set (list/JSON)
    result = runner.invoke(cli.app, ["profile", "set", "export.group_by", '["a", "b"]'])
    assert result.exit_code == 0
    result = runner.invoke(cli.app, ["profile", "get", "export.group_by"])
    assert result.exit_code == 0
    assert "['a', 'b']" in result.stdout

    # 存在しないキーへの get はエラー
    result = runner.invoke(cli.app, ["profile", "get", "invalid.key"])
    assert result.exit_code != 0
    assert "Error: Key 'invalid.key' not found in profile." in result.stdout

    # セクション（辞書）そのものの get はエラー
    result = runner.invoke(cli.app, ["profile", "get", "tui"])
    assert result.exit_code != 0
    assert "points to a section, not a specific value." in result.stdout

