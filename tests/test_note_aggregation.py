import pytest
from pathlib import Path

from work_time_logger import db, exporter, operations


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path: Path):
    test_db_dir = tmp_path / ".wtl_test"
    test_db_dir.mkdir()
    db.DB_DIR = test_db_dir
    db.DB_PATH = test_db_dir / "test_db.sqlite3"
    operations.setup()
    yield


def test_note_aggregation_with_multiple_logs(tmp_path: Path):
    # Create multiple logs with same content but different start times
    operations.add_project("PJ1")
    operations.add_job("Job1", "PJ1", code="JC01")

    # First log (1 hour)
    log1 = operations.create_empty_log()
    operations.update_log(
        log1, "PJ1", "Job1", "2024-01-01T10:00:00", "2024-01-01T11:00:00", "Memo A"
    )

    # Second log (1.5 hours, same memo)
    log2 = operations.create_empty_log()
    operations.update_log(
        log2, "PJ1", "Job1", "2024-01-01T13:00:00", "2024-01-01T14:30:00", "Memo A"
    )

    profile_path = tmp_path / "profile.toml"
    with open(profile_path, "w", encoding="utf-8") as f:
        f.write(
            """
[export.format]
note_item = "{{ memo }}: {{ time_hours }}h"
note_separator = " / "
[export.columns]
"notes" = "{{ aggregated_notes }}"
"""
        )

    _, results = exporter.aggregate_logs(str(profile_path))

    assert len(results) == 1
    # Expected: 1.0 + 1.5 = 2.5h is aggregated
    assert results[0]["notes"] == "Memo A: 2.5h"
