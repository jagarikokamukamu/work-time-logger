import os
import tomllib

import pytest
from typer.testing import CliRunner

from work_time_logger import db, operations
from work_time_logger.cli import app

runner = CliRunner()


@pytest.fixture
def setup_db(tmp_path):
    # Mock DB_DIR if needed, but here we can just use the real db for integration test
    # or rely on the fact that operations use get_connection.
    # For safety, we can just use the current env but clean up.
    pass


def test_job_list_codes():
    # Setup: Add project and job
    project_name = "TestProj"
    job_name = "TestJob"
    job_code = "123_456_BURDEN_CONTENT_PRE_BIKOU"

    try:
        operations.add_project(project_name)
    except:
        pass  # Already exists

    try:
        operations.add_job(job_name, project_name, code=job_code)
    except:
        pass  # Already exists

    # Run command
    result = runner.invoke(app, ["job", "list", "--codes", "--project", project_name])

    assert result.exit_code == 0
    # Check if key values are in output
    assert "123" in result.stdout
    assert "TestProj" in result.stdout
    assert "456" in result.stdout
    assert "BURDEN" in result.stdout
    assert "CONTENT" in result.stdout


if __name__ == "__main__":
    test_job_list_codes()
