from pathlib import Path
import pytest

from work_time_logger import db, operations


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path: Path):
    """Override the database path to use a temporary directory for tests"""
    test_db_dir = tmp_path / ".wtl_test"
    test_db_dir.mkdir()
    test_db_path = test_db_dir / "test_db.sqlite3"

    original_db_dir = db.DB_DIR
    original_db_path = db.DB_PATH

    db.DB_DIR = test_db_dir
    db.DB_PATH = test_db_path

    db.init_db()

    yield

    db.DB_DIR = original_db_dir
    db.DB_PATH = original_db_path


def test_undo_redo_start_log():
    # 1. Start a log (INSERT)
    log_id = operations.start_log(memo="Initial tracking")
    assert log_id == 1

    logs = operations.list_logs()
    assert len(logs) == 1
    assert logs[0]["memo"] == "Initial tracking"

    # 2. Undo the start
    undone = operations.undo()
    assert len(undone) == 1
    assert "Deleted log ID 1" in undone[0]

    logs = operations.list_logs()
    assert len(logs) == 0

    # 3. Redo the start
    redone = operations.redo()
    assert len(redone) == 1
    assert "Re-created log ID 1" in redone[0]

    logs = operations.list_logs()
    assert len(logs) == 1
    assert logs[0]["memo"] == "Initial tracking"


def test_undo_redo_stop_log():
    log_id = operations.start_log(memo="Tracking to stop")
    
    # Stop the log (UPDATE)
    operations.stop_log(log_id)
    
    logs = operations.list_logs()
    assert logs[0]["end_time"] is not None

    # Undo the stop
    undone = operations.undo()
    assert len(undone) == 1
    assert "Restored log ID 1 details" in undone[0]

    logs = operations.list_logs()
    assert logs[0]["end_time"] is None

    # Redo the stop
    redone = operations.redo()
    assert len(redone) == 1
    assert "Applied updates to log ID 1" in redone[0]

    logs = operations.list_logs()
    assert logs[0]["end_time"] is not None


def test_undo_redo_update_log():
    log_id = operations.start_log(memo="Original Memo")
    operations.stop_log(log_id)

    # Update log memo
    operations.update_log(log_id, memo="Updated Memo")
    
    logs = operations.list_logs()
    assert logs[0]["memo"] == "Updated Memo"

    # Undo the update
    undone = operations.undo()
    assert "Restored log ID 1 details" in undone[0]

    logs = operations.list_logs()
    assert logs[0]["memo"] == "Original Memo"

    # Redo the update
    redone = operations.redo()
    assert "Applied updates to log ID 1" in redone[0]

    logs = operations.list_logs()
    assert logs[0]["memo"] == "Updated Memo"


def test_undo_redo_delete_log():
    log_id = operations.start_log(memo="To be deleted")
    operations.stop_log(log_id)

    # Delete the log
    operations.delete_log(log_id)

    logs = operations.list_logs()
    assert len(logs) == 0

    # Undo the delete
    undone = operations.undo()
    assert "Restored deleted log ID 1" in undone[0]

    logs = operations.list_logs()
    assert len(logs) == 1
    assert logs[0]["memo"] == "To be deleted"

    # Redo the delete
    redone = operations.redo()
    assert "Re-deleted log ID 1" in redone[0]

    logs = operations.list_logs()
    assert len(logs) == 0


def test_history_rotation():
    # Execute 35 distinct actions
    for i in range(35):
        log_id = operations.start_log(memo=f"Action {i}")
        operations.stop_log(log_id)

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT group_id FROM operation_history")
        groups = cursor.fetchall()
        # Rotation should keep it to exactly 30 groups
        assert len(groups) == 30
