import pytest
from typer.testing import CliRunner

from work_time_logger import db, operations
from work_time_logger.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def setup_db(tmp_path):
    """Override symbols in the db module to use a temporary directory for tests"""
    test_db_dir = tmp_path / ".wtl_test"
    test_db_dir.mkdir()
    test_db_path = test_db_dir / "test_db.sqlite3"

    original_db_dir = db.DB_DIR
    original_db_path = db.DB_PATH

    db.DB_DIR = test_db_dir
    db.DB_PATH = test_db_path

    # Initialize the test database
    db.init_db()

    yield tmp_path

    # Cleanup: restore original paths
    db.DB_DIR = original_db_dir
    db.DB_PATH = original_db_path


def test_job_list_codes(setup_db):
    tmp_path = setup_db
    # Setup: Add project and job
    project_name = "TestProj"
    job_name = "TestJob"
    job_code = "123_456_BURDEN_CONTENT_PRE_BIKOU"

    operations.add_project(project_name)
    operations.add_job(job_name, project_name, code=job_code)

    # Create a temporary profile for list-codes
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text("""
[export.extract]
job_code = "(?P<proj>[A-Z0-9]+)_(?P<sub>[0-9]+)_(?P<cost>[A-Z]+)_\
(?P<prefix>[a-zA-Z]+)_(?P<desc>.*)"

[export.columns]
"proj" = "{{ proj }}"
"sub" = "{{ sub }}"
"cost" = "{{ cost }}"
"prefix" = "{{ prefix }}"
"desc" = "{{ desc }}"
""")

    # Run command
    result = runner.invoke(
        app,
        [
            "job",
            "list",
            "--codes",
            "--project",
            project_name,
            "--profile",
            str(profile_path),
        ],
    )

    assert result.exit_code == 0
    # Check if key values are in output (from job code expansion)
    assert "123" in result.stdout
    assert "TestJob" in result.stdout
    assert "456" in result.stdout
    assert "BURDEN" in result.stdout
    assert "CONTENT" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__])
