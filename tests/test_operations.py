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
    job_id = operations.add_job("Test Job", "Test Project", "A description")
    assert job_id == 1

    jobs = operations.list_jobs("Test Project")
    assert len(jobs) == 1
    assert jobs[0]["name"] == "Test Job"
    assert jobs[0]["description"] == "A description"


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
