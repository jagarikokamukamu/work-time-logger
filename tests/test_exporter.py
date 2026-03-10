import os
from pathlib import Path

import pytest

from work_time_logger import db, exporter, operations


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path: Path):
    test_db_dir = tmp_path / ".wtl_test"
    test_db_dir.mkdir()
    test_db_path = test_db_dir / "test_db.sqlite3"
    
    original_db_dir = db.DB_DIR
    original_db_path = db.DB_PATH

    db.DB_DIR = test_db_dir
    db.DB_PATH = test_db_path
    db.init_db()

    yield tmp_path

    db.DB_DIR = original_db_dir
    db.DB_PATH = original_db_path


def test_export_logic(tmp_path: Path):
    # Setup test data
    pid = operations.add_project("Project1")
    # Code matches the generic regex
    operations.add_job("Job1", "Project1", "desc1", "ABCD123_1000_XXX_PRE_Meeting")
    operations.add_job("Job2", "Project1", "desc2", "ABCD123_1000_XXX_PRE_Progress")
    operations.add_job("Job3", "Project1", "desc2", "ABCD123_2000_XXX_DEV_DesignDoc")
    
    pid2 = operations.add_project("Project2")
    operations.add_job("Job4", "Project2", "desc", "ABCD456_10_XXX_PRE_Meeting")

    # Log 1: Job1 (1.1 hours)
    log_id1 = operations.create_empty_log()
    operations.update_log(log_id1, "Project1", "Job1", "2024-01-01T10:00:00", "2024-01-01T11:06:00", "First meeting")
    
    # Log 2: Job2 (2.1 hours)
    log_id2 = operations.create_empty_log()
    operations.update_log(log_id2, "Project1", "Job2", "2024-01-01T13:00:00", "2024-01-01T15:06:00", "Status update")

    # Log 3: Job3 (1.2 hours)
    log_id3 = operations.create_empty_log()
    operations.update_log(log_id3, "Project1", "Job3", "2024-01-02T10:00:00", "2024-01-02T11:12:00", "Writing docs")

    # Log 4: Job4 (1.4 hours)
    log_id4 = operations.create_empty_log()
    operations.update_log(log_id4, "Project2", "Job4", "2024-01-03T10:00:00", "2024-01-03T11:24:00", "Kickoff")
    
    # Create export profile
    profile_path = tmp_path / "profile.toml"
    with open(profile_path, "w", encoding="utf-8") as f:
        f.write('''
[export.extract]
job_code = "(?P<proj>[A-Z0-9]+)_(?P<sub>[0-9]+)_(?P<cost>[A-Z]+)_(?P<prefix>[a-zA-Z]+)_(?P<desc>.*)"

[export.defaults]
"load" = "1"
"loss" = ""
"item" = ""
"work" = ""
"rev" = ""
"branch" = ""

[export]
group_by = [
    "proj", "sub", "load", "loss", "cost", "item", "work", "rev", "branch"
]

[export.format]
note_item = "({prefix}:{time_hours}):{desc}"
note_separator = "/"

[export.columns]
"proj" = "{proj}"
"subject" = "Proj_{proj}"
"sub" = "{sub}"
"load" = "{load}"
"loss" = "{loss}"
"cost" = "{cost}"
"item" = "{item}"
"work" = "{work}"
"rev" = "{rev}"
"desc" = "{desc}"
"branch" = "{branch}"
"time_col" = "{aggregated_time}"
"note_col" = "{aggregated_notes}"
        ''')
        
    output_path = tmp_path / "output.csv"
    
    count = exporter.export_logs(str(profile_path), str(output_path))
    assert count == 3
    
    with open(output_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "3.2" in content
    # Look for both orders since grouping output order might not be guaranteed
    assert "(PRE:1.1):Meeting/(PRE:2.1):Progress" in content or "(PRE:2.1):Progress/(PRE:1.1):Meeting" in content
