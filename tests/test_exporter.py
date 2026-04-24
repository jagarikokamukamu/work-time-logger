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
        log_id1,
        "Project1",
        "Job1",
        "2024-01-01T10:00:00",
        "2024-01-01T11:06:00",
        "First meeting",
    )

    # Log 2: Job2 (2.1 hours)
    log_id2 = operations.create_empty_log()
    operations.update_log(
        log_id2,
        "Project1",
        "Job2",
        "2024-01-01T13:00:00",
        "2024-01-01T15:06:00",
        "Status update",
    )

    # Log 3: Job3 (1.2 hours)
    log_id3 = operations.create_empty_log()
    operations.update_log(
        log_id3,
        "Project1",
        "Job3",
        "2024-01-02T10:00:00",
        "2024-01-02T11:12:00",
        "Writing docs",
    )

    # Log 4: Job4 (1.4 hours)
    log_id4 = operations.create_empty_log()
    operations.update_log(
        log_id4,
        "Project2",
        "Job4",
        "2024-01-03T10:00:00",
        "2024-01-03T11:24:00",
        "Kickoff",
    )

    # Create export profile
    profile_path = tmp_path / "profile.toml"
    with open(profile_path, "w", encoding="utf-8") as f:
        f.write("""
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
        """)

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


def test_auto_allocation_sweep_line(tmp_path: Path):
    from work_time_logger import exporter, operations

    operations.add_project("SweepProject")
    operations.add_job("JobA", "SweepProject", code="AUTO-100")
    operations.add_job("JobB", "SweepProject", code="AUTO-200")

    # overlaps
    # JobA: 10:00 - 12:00 (2h)
    # JobB: 11:00 - 13:00 (2h)
    # Expected Allocation:
    # 10:00 - 11:00 (1h) -> JobA = 1h
    # 11:00 - 12:00 (1h) -> JobA 0.5h, JobB 0.5h
    # 12:00 - 13:00 (1h) -> JobB = 1h
    # Total JobA = 1.5h, JobB = 1.5h

    log_a = operations.create_empty_log()
    operations.update_log(
        log_a, "SweepProject", "JobA", "2024-05-01T10:00:00", "2024-05-01T12:00:00"
    )

    log_b = operations.create_empty_log()
    operations.update_log(
        log_b, "SweepProject", "JobB", "2024-05-01T11:00:00", "2024-05-01T13:00:00"
    )

    profile_path = tmp_path / "profile.toml"
    with open(profile_path, "w", encoding="utf-8") as f:
        f.write("""
[export.extract]
job_code = "^(?P<kind>[A-Z]+)-(?P<num>\\\\d+)$"

[export]
group_by = ["kind", "num"]

[export.columns]
"Job" = "{{ num }}"
"Allocated" = "{{ aggregated_time }}"
""")

    output_path = tmp_path / "output_sweep.csv"
    exporter.export_logs(str(profile_path), str(output_path), target_date="2024-05-01")

    with open(output_path, encoding="utf-8") as f:
        content = f.read()

    assert "100,1.5" in content
    assert "200,1.5" in content


def test_time_precision_and_rounding(tmp_path: Path):
    """time_precision and time_rounding should affect aggregated_time correctly."""
    operations.add_project("PrecProject")
    # duration_hours=2.16: has 2 decimal places, so precision=1 will actually round it
    # As a float, 2.16 ≈ 2.1599..., which is > 2.15,
    # so round(2.16, 1) = 2.2 deterministically
    operations.add_job("JobA", "PrecProject", code="T-001")
    log_id = operations.create_empty_log()
    operations.update_log(
        log_id,
        "PrecProject",
        "JobA",
        "2024-02-01T10:00:00",
        "2024-02-01T10:00:00",
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
    assert get_time_col(c) == 2.2  # aggregated_time
    assert get_note_col(c) == 2.2  # time_hours in note_item

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
            lid,
            "AggProject",
            "Job1",
            "2024-03-01T10:00:00",
            "2024-03-01T10:00:00",
            duration_hours=1.16,
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
        f.write("""
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
""")

    output_path = tmp_path / "jobs_export.csv"

    count = exporter.export_jobs(
        str(profile_path), str(output_path), project_name="ProjectA"
    )
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


def test_get_job_import_row(tmp_path: Path):
    """Test retrieving a single job row in import-compatible format."""
    operations.add_project("ProjB")
    operations.add_job("JobB1", "ProjB", "memo B1", "KIND_123_EXT")

    profile_path = tmp_path / "profile_import.toml"
    with open(profile_path, "w", encoding="utf-8") as f:
        f.write(
            """
[export.extract]
job_code = "^(?P<pfx>[A-Z]+)_(?P<n>\\\\d+)_(?P<s>[A-Z]+)$"

[import.mapping]
name = "{{ 表示名 }}"
job_code = "{{ pfx }}_{{ n }}_{{ s }}"
"""
        )

    profile = exporter.load_profile(str(profile_path))
    cols, row, _ = exporter.get_job_import_row(profile, "ProjB", "JobB1")

    assert "表示名" in cols
    assert "pfx" in cols
    assert row["表示名"] == "JobB1"
    assert row["pfx"] == "KIND"
    assert row["n"] == "123"
    assert row["s"] == "EXT"


def test_update_job_from_import_row(tmp_path: Path):
    """Test updating a job's description and code from an import-style row."""
    operations.add_project("ProjC")
    operations.add_job("JobC1", "ProjC", "old desc", "OLD_CODE")

    profile_path = tmp_path / "profile_update.toml"
    with open(profile_path, "w", encoding="utf-8") as f:
        f.write(
            """
[import.mapping]
description = "New: {{ note }}"
job_code = "NEW_{{ num }}"
"""
        )

    profile = exporter.load_profile(str(profile_path))
    updated_row = {"note": "updated memo", "num": "999"}

    exporter.update_job_from_import_row(profile, "ProjC", "JobC1", updated_row)

    # Verify DB update
    jobs = operations.list_jobs("ProjC")
    job = next((j for j in jobs if j["name"] == "JobC1"), None)
    assert job is not None
    assert job["description"] == "New: updated memo"
    assert job["code"] == "NEW_999"
def test_time_aggregation_method_subtotal(tmp_path: Path):
    """Test round_subtotal_then_sum method.
    It should round the sum of raw hours for each sub-group (memo),
    then sum those rounded subtotals.
    """
    operations.add_project("AggSubProject")
    operations.add_job("Job1", "AggSubProject", code="T-001")

    # Grouping:
    # Subgroup A (Memo A): 0.55 + 0.55 = 1.10. Round(1, 1) -> 1.1
    # Subgroup B (Memo B): 0.44 + 0.44 = 0.88. Round(1, 1) -> 0.9
    # Total aggregated_time: 1.1 + 0.9 = 2.0

    # For comparison:
    # sum_then_round: (0.55*2 + 0.44*2) = 1.10 + 0.88 = 1.98 -> 2.0
    # (In this specific case it might hit the same, but let's use values that differ)

    # Let's adjust values:
    # Sub A: 1.16 + 1.16 = 2.32 -> Round(1) = 2.3
    # Sub B: 1.16 + 1.16 = 2.32 -> Round(1) = 2.3
    # sum_then_round: (1.16*4) = 4.64 -> 4.6
    # round_then_sum: 1.2 * 4 = 4.8
    # round_subtotal_then_sum: 2.3 + 2.3 = 4.6

    # Wait, let's find values where all three differ:
    # Sub A: 1.14 + 1.14 = 2.28 -> SubRound=2.3, LogRound=1.1,1.1 Sum=2.2
    # Sub B: 1.14 + 1.14 = 2.28 -> SubRound=2.3, LogRound=1.1,1.1 Sum=2.2
    # sum_then_round: 2.28 * 2 = 4.56 -> 4.6
    # round_then_sum: 1.1 * 4 = 4.4
    # round_subtotal_then_sum: 2.3 + 2.3 = 4.6 (Still same as sum_then_round here)

    # Let's try:
    # Sub A: 1.04 + 1.04 = 2.08 -> SubRound=2.1, LogRound=1.0,1.0 Sum=2.0
    # Sub B: 1.04 + 1.04 = 2.08 -> SubRound=2.1, LogRound=1.0,1.0 Sum=2.0
    # sum_then_round: 2.08 * 2 = 4.16 -> 4.2
    # round_then_sum: 1.0 * 4 = 4.0
    # round_subtotal_then_sum: 2.1 + 2.1 = 4.2

    # One more try for distinct:
    # Sub A: 1.05 + 1.05 = 2.10 -> SubRound=2.1, LogRound=1.1,1.1 Sum=2.2
    # Sub B: 1.05 + 1.05 = 2.10 -> SubRound=2.1, LogRound=1.1,1.1 Sum=2.2
    # sum_then_round: 2.10 * 2 = 4.20 -> 4.2
    # round_then_sum: 1.1 * 4 = 4.4
    # round_subtotal_then_sum: 2.1 + 2.1 = 4.2

    # Okay, distinct enough to tell round_then_sum apart.
    # To tell sum_then_round and round_subtotal_then_sum apart:
    # Sub A: 1.06 + 1.06 = 2.12 -> SubRound=2.1, LogRound=1.1,1.1 Sum=2.2
    # Sub B: 1.06 + 1.06 = 2.12 -> SubRound=2.1, LogRound=1.1,1.1 Sum=2.2
    # Total Raw = 4.24 -> sum_then_round = 4.2
    # round_subtotal_then_sum = 2.1 + 2.1 = 4.2

    # Actually, most of the time sum_then_round and round_subtotal_then_sum are close.
    # The key is that round_subtotal_then_sum matches the notes.

    for memo in ["Memo A", "Memo B"]:
        for _ in range(2):
            lid = operations.create_empty_log()
            operations.update_log(
                lid,
                "AggSubProject",
                "Job1",
                "2024-04-01T10:00:00",
                "2024-04-01T10:00:00",
                memo=memo,
                duration_hours=1.06,
            )

    profile_path = tmp_path / "profile_sub.toml"

    def run_export_sub(method: str) -> tuple[float, list[str]]:
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(f"""
[export.extract]
job_code = "^(?P<kind>[A-Z]+)-(?P<num>\\\\d+)$"
[export]
group_by = ["kind"]
time_precision = 1
time_rounding = "round"
time_aggregation_method = "{method}"
[export.format]
note_item = "{{{{ time_hours }}}}"
note_separator = "/"
[export.columns]
"time" = "{{{{ aggregated_time }}}}"
"notes" = "{{{{ aggregated_notes }}}}"
""")
        out = tmp_path / f"out_sub_{method}.csv"
        exporter.export_logs(str(profile_path), str(out), target_date=None)
        with open(out, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            row = next(reader)
            return float(row["time"]), row["notes"].split("/")

    # round_then_sum: each log 1.06 -> 1.1.
    # Total aggregated_time = (1.1 * 4) = 4.4
    # Note logic: subtotals are sum of rounded logs, so 1.1 + 1.1 = 2.2
    t1, n1 = run_export_sub("round_then_sum")
    assert t1 == 4.4
    assert all(val == "2.2" for val in n1)

    # sum_then_round: (1.06 * 4) = 4.24 -> 4.2.
    # Note logic: raw sum then round, so (1.06 + 1.06) = 2.12 -> 2.1
    t2, n2 = run_export_sub("sum_then_round")
    assert t2 == 4.2
    assert all(val == "2.1" for val in n2)

    # round_subtotal_then_sum: (1.06 + 1.06) = 2.12 -> 2.1.
    # Total aggregated_time = 2.1 + 2.1 = 4.2
    t3, n3 = run_export_sub("round_subtotal_then_sum")
    assert t3 == 4.2
    assert all(val == "2.1" for val in n3)

    # Let's find a case where sum_then_round and round_subtotal_then_sum differ:
    # Sub A: 1.04 + 1.04 = 2.08 -> 2.1
    # Sub B: 1.04 + 1.04 = 2.08 -> 2.1
    # Total Raw = 4.16 -> sum_then_round = 4.2
    # round_subtotal_then_sum = 2.1 + 2.1 = 4.2 (Still same...)

    # Case:
    # Sub A: 1.03 (1 log) -> 1.0
    # Sub B: 1.03 (1 log) -> 1.0
    # Total Raw = 2.06 -> sum_then_round = 2.1
    # round_subtotal_then_sum = 1.0 + 1.0 = 2.0
    # (With precision=1, round)

    operations.add_project("DiffProject")
    operations.add_job("Job1", "DiffProject", code="D-001")
    for memo in ["M1", "M2"]:
        lid = operations.create_empty_log()
        operations.update_log(
            lid, "DiffProject", "Job1", "2024-04-02T10:00:00", "2024-04-02T10:00:00",
            memo=memo, duration_hours=1.03
        )

    def run_export_diff(method: str) -> float:
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
        out = tmp_path / f"out_diff_{method}.csv"
        exporter.export_logs(str(profile_path), str(out), target_date=None)
        with open(out, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            row = next(reader)
            return float(row["time"])

    assert run_export_diff("sum_then_round") == 2.1
    assert run_export_diff("round_subtotal_then_sum") == 2.0


def test_floor_rounding_precision_bug(tmp_path: Path):
    """Test that floor rounding with float accumulation doesn't cause a precision drop

    (e.g., 4.0 + 0.3 + 0.3 + 0.3 = 4.8999999999999995 should floor to 4.9, not 4.8)
    """
    operations.add_project("BugProject")
    # job_code extracts: Proj, Detail, Burden, Work
    operations.add_job("JobA", "BugProject", code="0000_1000_XXX_ProjMgmt")
    operations.add_job("JobB", "BugProject", code="0000_1000_XXX_ProjMgmt")
    operations.add_job("JobC", "BugProject", code="0000_1000_XXX_DetailDesign")

    # A: 4 hours (16:00 - 20:00)
    lid_a1 = operations.create_empty_log()
    operations.update_log(
        lid_a1, "BugProject", "JobA", "2026-06-16T16:00:00", "2026-06-16T20:00:00"
    )

    # ABC: 1 hour overlap (20:00 - 21:00) -> 1/3 hours each
    lid_a2 = operations.create_empty_log()
    operations.update_log(
        lid_a2, "BugProject", "JobA", "2026-06-16T20:00:00", "2026-06-16T21:00:00"
    )
    lid_b = operations.create_empty_log()
    operations.update_log(
        lid_b, "BugProject", "JobB", "2026-06-16T20:00:00", "2026-06-16T21:00:00"
    )
    lid_c = operations.create_empty_log()
    operations.update_log(
        lid_c, "BugProject", "JobC", "2026-06-16T20:00:00", "2026-06-16T21:00:00"
    )

    profile_path = tmp_path / "profile_bug.toml"
    with open(profile_path, "w", encoding="utf-8") as f:
        f.write("""
[export.extract]
job_code = "^(?P<construction_no>[^_]*)_(?P<detail_no>[^_]*)_(?P<burden>[^_]*)_(?P<work_content>[^_]*)$"

[export]
group_by = ["construction_no", "detail_no", "burden", "work_content"]
time_precision = 1
time_rounding = "floor"
time_aggregation_method = "round_subtotal_then_sum"

[export.columns]
"time" = "{{ aggregated_time }}"
""")

    out = tmp_path / "out_bug.csv"
    exporter.export_logs(str(profile_path), str(out), target_date="2026-06-16")
    with open(out, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # There should be two rows:
    # 1. ProjMgmt: A(4.0) + A(0.3) + B(0.3) = 4.6
    # 2. DetailDesign: C(0.3)
    # Total sum of these sub-group columns in DailySummary: 4.6 + 0.3 = 4.9.
    # Note that the subtotal_sum_for_agg within ProjMgmt: A(4.0 + 0.3) + B(0.3) = 4.3 + 0.3 = 4.6.
    # With floating point error, 4.3 + 0.3 could be 4.5999999999999996, which floors to 4.5.
    # We assert it properly yields 4.6.
    proj_mgmt_row = next(r for r in rows if r["time"] != "0.3")
    assert float(proj_mgmt_row["time"]) == 4.6
