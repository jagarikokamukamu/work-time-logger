from pathlib import Path

import pytest

from work_time_logger import db, operations


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path: Path):
    """Override the database path to use a temporary directory for tests"""
    # Create a temporary directory for the DB
    test_db_dir = tmp_path / ".wtl_test"
    test_db_dir.mkdir()
    test_db_path = test_db_dir / "test_db.sqlite3"

    # Override paths in the db module
    original_db_dir = db.DB_DIR
    original_db_path = db.DB_PATH

    db.DB_DIR = test_db_dir
    db.DB_PATH = test_db_path

    # Initialize the test database
    db.init_db()

    yield

    # Cleanup: restore original paths (temp files are cleaned by pytest)
    db.DB_DIR = original_db_dir
    db.DB_PATH = original_db_path


def test_add_project_and_job():
    # Test Adding a Project
    project_id = operations.add_project("Test Project")
    assert project_id == 1

    projects = operations.list_projects()
    assert len(projects) == 1
    assert projects[0]["name"] == "Test Project"

    # Test Adding a Job
    job_id = operations.add_job(
        "Test Job", "Test Project", "A description", "JOB_CODE_01"
    )
    assert job_id == 1

    jobs = operations.list_jobs("Test Project")
    assert len(jobs) == 1
    assert jobs[0]["name"] == "Test Job"
    assert jobs[0]["description"] == "A description"
    assert jobs[0]["code"] == "JOB_CODE_01"


def test_start_unassigned_job():
    log_id = operations.start_log()
    assert log_id == 1

    logs = operations.list_logs()
    assert len(logs) == 1
    assert logs[0]["project_name"] is None
    assert logs[0]["job_name"] is None
    assert logs[0]["end_time"] is None

    operations.stop_log()
    logs = operations.list_logs()
    assert logs[0]["end_time"] is not None


def test_prevent_double_start():
    operations.start_log()
    with pytest.raises(ValueError, match="A job is already running"):
        operations.start_log()


def test_assign_log_later():
    # Start unassigned
    log_id = operations.start_log()

    # Create project and job
    operations.add_project("P1")
    operations.add_job("J1", "P1")

    # Assign it
    operations.assign_log(log_id, "P1", "J1")

    logs = operations.list_logs()
    assert logs[0]["project_name"] == "P1"
    assert logs[0]["job_name"] == "J1"


def test_delete_project_cascades():
    p_id = operations.add_project("Del Project")
    operations.add_job("Del Job", "Del Project")
    operations.start_log("Del Project", "Del Job")
    operations.stop_log()

    operations.delete_project(p_id)

    assert len(operations.list_projects()) == 0
    assert len(operations.list_jobs("Del Project")) == 0
    assert len(operations.list_logs()) == 0


def test_delete_log():
    operations.create_empty_log()
    logs = operations.list_logs()
    assert len(logs) == 1
    log_id = logs[0]["id"]

    operations.delete_log(log_id)
    assert len(operations.list_logs()) == 0

    with pytest.raises(ValueError, match="Log ID 999 not found"):
        operations.delete_log(999)


def test_update_log():
    operations.create_empty_log()
    logs = operations.list_logs()
    log_id = logs[0]["id"]

    operations.add_project("UpdateProj")
    operations.add_job("UpdateJob", "UpdateProj")

    operations.update_log(
        log_id,
        project_name="UpdateProj",
        job_name="UpdateJob",
        start_time="2024-01-01T10:00:00",
        end_time=None,
        memo="updated memo",
    )

    updated_log = operations.list_logs()[0]
    assert updated_log["project_name"] == "UpdateProj"
    assert updated_log["job_name"] == "UpdateJob"
    assert updated_log["start_time"] == "2024-01-01T10:00:00"
    assert updated_log["end_time"] is None
    assert updated_log["memo"] == "updated memo"


def test_create_assigned_log(setup_test_db):
    """Test that a log with pre-assigned project/job is created correctly."""
    operations.add_project("Proj")
    operations.add_job("Job", "Proj")
    operations.create_assigned_log("Proj", "Job")

    logs = operations.list_logs()
    assert len(logs) == 1
    assert logs[0]["project_name"] == "Proj"
    assert logs[0]["job_name"] == "Job"
    assert logs[0]["duration_hours"] == 0.0


def test_update_log_preserves_duration(setup_test_db):
    """Test that updating a log (e.g., memo) does not
    reset manually entered duration."""
    operations.add_project("P")
    operations.add_job("J", "P")
    operations.start_log("P", "J")
    operations.stop_log()

    logs = operations.list_logs()
    log_id = logs[0]["id"]

    # Set manual duration
    operations.update_log(
        log_id, "P", "J", logs[0]["start_time"], logs[0]["end_time"],
        duration_hours=5.5
    )

    # Update memo only
    operations.update_log(
        log_id, "P", "J", logs[0]["start_time"], logs[0]["end_time"],
        memo="Updated Memo"
    )

    # Check if duration is still 5.5
    updated_logs = operations.list_logs()
    assert updated_logs[0]["duration_hours"] == 5.5
    assert updated_logs[0]["memo"] == "Updated Memo"
