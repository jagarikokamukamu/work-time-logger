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

    operations.stop_all_logs()
    logs = operations.list_logs()
    assert logs[0]["end_time"] is not None


def test_prevent_double_start():
    operations.start_log()
    with pytest.raises(ValueError, match="A job is already running"):
        operations.start_log()


def test_allow_double_start_with_force_parallel():
    log_1 = operations.start_log()
    # Second one can be started if force_parallel=True
    log_2 = operations.start_log(force_parallel=True)
    assert log_1 != log_2

    logs = operations.list_logs()
    # There should be two running logs
    running = [log for log in logs if log["end_time"] is None]
    assert len(running) == 2


def test_stop_specific_log():
    log_1 = operations.start_log()
    log_2 = operations.start_log(force_parallel=True)

    # Stop only log_1
    operations.stop_log(log_id=log_1)

    logs = operations.list_logs()
    log_1_entry = next(log for log in logs if log["id"] == log_1)
    log_2_entry = next(log for log in logs if log["id"] == log_2)

    assert log_1_entry["end_time"] is not None
    assert log_2_entry["end_time"] is None

    # Finally stop the remaining Running log (log_2) without arguments
    operations.stop_all_logs()
    logs = operations.list_logs()
    log_2_entry = next(log for log in logs if log["id"] == log_2)
    assert log_2_entry["end_time"] is not None


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
    operations.stop_all_logs()

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
    assert logs[0]["duration_hours"] is None


def test_update_log_preserves_duration(setup_test_db):
    """Test that updating a log (e.g., memo) does not
    reset manually entered duration."""
    operations.add_project("P")
    operations.add_job("J", "P")
    operations.start_log("P", "J")
    operations.stop_all_logs()

    logs = operations.list_logs()
    log_id = logs[0]["id"]

    # Set manual duration
    operations.update_log(
        log_id, "P", "J", logs[0]["start_time"], logs[0]["end_time"], duration_hours=5.5
    )

    # Update memo only
    operations.update_log(
        log_id,
        "P",
        "J",
        logs[0]["start_time"],
        logs[0]["end_time"],
        memo="Updated Memo",
    )

    # Check if duration is still 5.5
    updated_logs = operations.list_logs()
    assert updated_logs[0]["duration_hours"] == 5.5
    assert updated_logs[0]["memo"] == "Updated Memo"


def test_parse_smart_date():
    from datetime import date, timedelta

    today = date.today()

    # Static keywords
    assert operations.parse_smart_date("today") == today.isoformat()
    expected_yest = (today - timedelta(days=1)).isoformat()
    assert operations.parse_smart_date("yesterday") == expected_yest
    assert operations.parse_smart_date("yest") == expected_yest

    # Relative days
    assert operations.parse_smart_date("+1") == (today + timedelta(days=1)).isoformat()
    assert operations.parse_smart_date("-2") == (today - timedelta(days=2)).isoformat()

    # M/D or M-D
    expected_3_26 = date(today.year, 3, 26).isoformat()
    assert operations.parse_smart_date("3/26") == expected_3_26
    assert operations.parse_smart_date("03-26") == expected_3_26
    assert operations.parse_smart_date("3.26") == expected_3_26

    # MMDD
    assert operations.parse_smart_date("0326") == expected_3_26

    # D or DD (current month)
    expected_15 = date(today.year, today.month, 15).isoformat()
    assert operations.parse_smart_date("15") == expected_15

    # ISO fallback
    assert operations.parse_smart_date("2023-12-25") == "2023-12-25"

    # Invalid
    assert operations.parse_smart_date("invalid") is None
    assert operations.parse_smart_date("13/32") is None  # Invalid day
