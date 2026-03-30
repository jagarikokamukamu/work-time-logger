import csv
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
    operations.add_project("Project1")
    # Code matches the generic regex
    operations.add_job("Job1", "Project1", "desc1", "ABCD123_1000_XXX_PRE_Meeting")
    operations.add_job("Job2", "Project1", "desc2", "ABCD123_1000_XXX_PRE_Progress")
    operations.add_job("Job3", "Project1", "desc2", "ABCD123_2000_XXX_DEV_DesignDoc")

    operations.add_project("Project2")
    operations.add_job("Job4", "Project2", "desc", "ABCD456_10_XXX_PRE_Meeting")

    # Log 1: Job1 (1.1 hours)
    log_id1 = operations.create_empty_log()
    operations.update_log(
        log_id1, "Project1", "Job1", "2024-01-01T10:00:00",
        "2024-01-01T11:06:00", "First meeting"
    )

    # Log 2: Job2 (2.1 hours)
    log_id2 = operations.create_empty_log()
    operations.update_log(
        log_id2, "Project1", "Job2", "2024-01-01T13:00:00",
        "2024-01-01T15:06:00", "Status update"
    )

    # Log 3: Job3 (1.2 hours)
    log_id3 = operations.create_empty_log()
    operations.update_log(
        log_id3, "Project1", "Job3", "2024-01-02T10:00:00",
        "2024-01-02T11:12:00", "Writing docs"
    )

    # Log 4: Job4 (1.4 hours)
    log_id4 = operations.create_empty_log()
    operations.update_log(
        log_id4, "Project2", "Job4", "2024-01-03T10:00:00",
        "2024-01-03T11:24:00", "Kickoff"
    )

    # Create export profile
    profile_path = tmp_path / "profile.toml"
    with open(profile_path, "w", encoding="utf-8") as f:
        f.write('''
[export.extract]
job_code = "(?P<proj>[A-Z0-9]+)_(?P<sub>[0-9]+)_(?P<cost>[A-Z]+)_\
(?P<prefix>[a-zA-Z]+)_(?P<desc>.*)"

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
note_item = "({{ prefix }}:{{ time_hours }}):{{ desc }}"
note_separator = "/"

[export.columns]
"proj" = "{{ proj }}"
"subject" = "Proj_{{ proj }}"
"sub" = "{{ sub }}"
"load" = "{{ load }}"
"loss" = "{{ loss }}"
"cost" = "{{ cost }}"
"item" = "{{ item }}"
"work" = "{{ work }}"
"rev" = "{{ rev }}"
"desc" = "{{ desc }}"
"branch" = "{{ branch }}"
"time_col" = "{{ aggregated_time }}"
"note_col" = "{{ aggregated_notes }}"
        ''')

    output_path = tmp_path / "output.csv"

    count = exporter.export_logs(str(profile_path), str(output_path), target_date=None)
    assert count == 3

    with open(output_path, encoding="utf-8") as f:
        content = f.read()

    assert "3.2" in content
    # Look for both orders since grouping output order might not be guaranteed
    assert (
        "(PRE:1.1):Meeting/(PRE:2.1):Progress" in content
        or "(PRE:2.1):Progress/(PRE:1.1):Meeting" in content
    )


def test_time_precision_and_rounding(tmp_path: Path):
    """time_precision and time_rounding should affect aggregated_time correctly."""
    operations.add_project("PrecProject")
    # duration_hours=2.16: has 2 decimal places, so precision=1 will actually round it
    # As a float, 2.16 ≈ 2.1599..., which is > 2.15,
    # so round(2.16, 1) = 2.2 deterministically
    operations.add_job("JobA", "PrecProject", code="T-001")
    log_id = operations.create_empty_log()
    operations.update_log(
        log_id, "PrecProject", "JobA",
        "2024-02-01T10:00:00", "2024-02-01T10:00:00",
        "task",
        duration_hours=2.16,
    )

    profile_path = tmp_path / "profile.toml"

    def run_export(precision: int, rounding: str) -> str:
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(f"""
[export.extract]
job_code = "^(?P<kind>[A-Z]+)-(?P<num>\\\\d+)$"
[export]
group_by = ["kind"]
time_precision = {precision}
time_rounding = "{rounding}"
[export.format]
note_item = "{{{{ time_hours }}}}"
note_separator = "/"
[export.columns]
"time" = "{{{{ aggregated_time }}}}"
"note" = "{{{{ aggregated_notes }}}}"
""")
        out = tmp_path / f"out_{precision}_{rounding}.csv"
        exporter.export_logs(str(profile_path), str(out), target_date=None)
        return out.read_text(encoding="utf-8")

    def get_time_col(content: str) -> float:
        """Extract the 'time' column value from the first data row."""
        data_row = content.strip().split("\n")[1]
        return float(data_row.split(",")[0])

    def get_note_col(content: str) -> float:
        """Extract the 'note' column (time_hours in note_item)
        from the first data row."""
        data_row = content.strip().split("\n")[1]
        return float(data_row.split(",")[1])

    # precision=1, round -> 2.16 rounds to 2.2
    # Verifies BOTH aggregated_time AND time_hours in note_item are rounded
    c = run_export(1, "round")
    assert get_time_col(c) == 2.2       # aggregated_time
    assert get_note_col(c) == 2.2       # time_hours in note_item

    # precision=0, floor -> 2.16 floors to 2
    assert get_time_col(run_export(0, "floor")) == 2.0

    # precision=0, ceil -> 2.16 ceils to 3
    assert get_time_col(run_export(0, "ceil")) == 3.0


def test_time_aggregation_method(tmp_path: Path):
    """Test sum_then_round vs round_then_sum methods."""
    operations.add_project("AggProject")
    operations.add_job("Job1", "AggProject", code="T-001")

    # Add two logs: 1.16 + 1.16 = 2.32
    # Rounding to precision=1:
    # sum_then_round: round(2.32, 1) = 2.3
    # round_then_sum: round(1.16, 1) + round(1.16, 1) = 1.2 + 1.2 = 2.4

    for _ in range(2):
        lid = operations.create_empty_log()
        operations.update_log(
            lid, "AggProject", "Job1",
            "2024-03-01T10:00:00", "2024-03-01T10:00:00",
            duration_hours=1.16
        )

    profile_path = tmp_path / "profile.toml"

    def run_export_method(method: str) -> float:
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(f"""
[export.extract]
job_code = "^(?P<kind>[A-Z]+)-(?P<num>\\\\d+)$"
[export]
group_by = ["kind"]
time_precision = 1
time_rounding = "round"
time_aggregation_method = "{method}"
[export.columns]
"time" = "{{{{ aggregated_time }}}}"
""")
        out = tmp_path / f"out_{method}.csv"
        exporter.export_logs(str(profile_path), str(out), target_date=None)
        content = out.read_text(encoding="utf-8")
        data_row = content.strip().split("\n")[1]
        return float(data_row.split(",")[0])

    assert run_export_method("sum_then_round") == 2.3
    assert run_export_method("round_then_sum") == 2.4


def test_export_jobs(tmp_path: Path):
    """Test the smart job export functionality based on import mapping."""
    operations.add_project("ProjectA")
    # Code matches the import structure: {Prefix}_{Number}_{Suffix}
    # We'll use Japanese names in mapping to mimic the user's issue
    operations.add_job("JobA1", "ProjectA", "desc A1", "KIND_001_SUB")

    profile_path = tmp_path / "profile.toml"
    with open(profile_path, "w", encoding="utf-8") as f:
        f.write('''
[export.extract]
job_code = "^(?P<pfx>[A-Z]+)_(?P<n>\\\\d+)_(?P<s>[A-Z]+)$"

[import.mapping]
name = "{{ 表示名 }}"
description = "{{ メモ }}"
job_code = "{{ 接頭語 }}_{{ 番号 }}_{{ 枝番 }}"

[export.columns]
"接頭語" = "{{ pfx }}"
"番号" = "{{ n }}"
"枝番" = "{{ s }}"
''')

    output_path = tmp_path / "jobs_export.csv"

    count = exporter.export_jobs(str(profile_path), str(output_path), project_name="ProjectA")
    assert count == 1

    with open(output_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 1
    # Check headers derived from mapping
    assert "表示名" in rows[0]
    assert "接頭語" in rows[0]
    assert "番号" in rows[0]
    assert "枝番" in rows[0]
    assert "メモ" in rows[0]

    # Values
    assert rows[0]["表示名"] == "JobA1"
    assert rows[0]["接頭語"] == "KIND"
    assert rows[0]["番号"] == "001"
    assert rows[0]["枝番"] == "SUB"
    assert rows[0]["メモ"] == "desc A1"
