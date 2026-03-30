"""Core business logic and database operations for Work Time Logger."""

import csv
from datetime import datetime

from jinja2 import Environment, Undefined

from .db import get_connection, init_db

# Security: Enable autoescape to prevent XSS (Bandit B701)
# Use a silent Undefined so missing vars render as empty string
_jinja_env = Environment(undefined=Undefined, autoescape=True)


def setup():
    """Initialize the database configuration and tables.

    This function sets up the base directory and creates the SQLite tables
    if they do not already exist.
    """
    init_db()


def add_project(name: str):
    """Add a new project to the database.

    Args:
        name (str): The name of the project.

    Returns:
        int: The ID of the newly created project.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO projects (name) VALUES (?)", (name,))
        conn.commit()
        return cursor.lastrowid


def list_projects():
    """List all projects in the database.

    Returns:
        list[sqlite3.Row]: A list of project records.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM projects")
        return cursor.fetchall()


def delete_project(project_id: int):
    """Delete a project by its ID, cascading deletes to its jobs and logs.

    Args:
        project_id (int): The internal ID of the project to delete.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()


def add_job(name: str, project_name: str, description: str = "", code: str = None):
    """Add a new job under a specific project.

    Args:
        name (str): The name of the job.
        project_name (str): The name of the project the job belongs to.
        description (str, optional): A brief description of the job. Defaults to "".
        code (str, optional): An external reference code (e.g., JIRA ticket).
            Defaults to None.

    Returns:
        int: The ID of the newly created job.

    Raises:
        ValueError: If the project name is not found in the database.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
        result = cursor.fetchone()
        if not result:
            raise ValueError(f"Project '{project_name}' not found.")
        project_id = result["id"]
        cursor.execute(
            "INSERT INTO jobs (project_id, name, description, code) "
            "VALUES (?, ?, ?, ?)",
            (project_id, name, description, code),
        )
        conn.commit()
        return cursor.lastrowid


def list_jobs(project_name: str = None):
    """List all jobs, optionally filtering by project name.

    Args:
        project_name (str, optional): The name of the project to filter by.
            Defaults to None.

    Returns:
        list[sqlite3.Row]: A list of job records with joined project names.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        if project_name:
            cursor.execute(
                """
                SELECT jobs.*, projects.name as project_name
                FROM jobs
                JOIN projects ON jobs.project_id = projects.id
                WHERE projects.name = ?
            """,
                (project_name,),
            )
        else:
            cursor.execute("""
                SELECT jobs.*, projects.name as project_name
                FROM jobs
                JOIN projects ON jobs.project_id = projects.id
            """)
        return cursor.fetchall()


def delete_job(job_id: int):
    """Delete a job by its ID.

    Args:
        job_id (int): The internal ID of the job to delete.

    Raises:
        ValueError: If the job ID is not found.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        if cursor.rowcount == 0:
            raise ValueError(f"Job ID {job_id} not found.")
        conn.commit()


def import_jobs_from_csv(
    filepath: str, project_name: str, profile_path: str = None
) -> int:
    """Import jobs from a CSV file into a given project.

    This function uses a TOML profile to map CSV columns to job attributes
    (name, description, code) using Jinja2 templates.

    Args:
        filepath (str): Path to the source CSV file.
        project_name (str): Target project name.
        profile_path (str, optional): Path to the mapping TOML profile.
            Defaults to None.

    Returns:
        int: Number of jobs successfully imported.

    Raises:
        ValueError: If the project name is not found.
    """
    import os
    import tomllib

    def render(template_str: str, context: dict) -> str | None:
        if not template_str:
            return None
        try:
            return _jinja_env.from_string(template_str).render(**context) or None
        except Exception:
            return None

    mapping = {
        "name": "{{ name }}",
        "description": "{{ description }}",
        "code": "{{ code }}",
    }

    if profile_path and os.path.exists(profile_path):
        try:
            with open(profile_path, "rb") as f:
                profile = tomllib.load(f)
                import_mapping = profile.get("import", {}).get("mapping", {})
                if import_mapping:
                    if "name" in import_mapping:
                        mapping["name"] = import_mapping["name"]
                    if "description" in import_mapping:
                        mapping["description"] = import_mapping["description"]
                    if "job_code" in import_mapping:
                        mapping["code"] = import_mapping["job_code"]
        except (OSError, tomllib.TOMLDecodeError):
            # Profile is optional or might be malformed; defaults are used.
            # This is a safe fallback and doesn't mask critical security issues.
            pass

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
        result = cursor.fetchone()
        if not result:
            raise ValueError(f"Project '{project_name}' not found.")
        project_id = result["id"]

        with open(filepath, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                ctx = dict(row)

                name = render(mapping["name"], ctx)
                if not name:
                    name = row.get("name")
                if not name:
                    continue

                description = render(mapping["description"], ctx) or row.get(
                    "description", ""
                )
                code = render(mapping["code"], ctx) or row.get("code")

                try:
                    cursor.execute(
                        "INSERT INTO jobs (project_id, name, description, code) "
                        "VALUES (?, ?, ?, ?)",
                        (project_id, name, description, code),
                    )
                    count += 1
                except Exception:
                    # During import, we skip rows that are invalid (e.g. duplicates)
                    # to allow the rest of the import to proceed.
                    # nosec B110, B112
                    continue
        conn.commit()
        return count


def is_any_job_running() -> bool:
    """Check if there is currently a running (active) log entry.

    Returns:
        bool: True if a job is currently running, False otherwise.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM logs WHERE end_time IS NULL")
        return cursor.fetchone() is not None


def start_log(project_name: str = None, job_name: str = None):
    """Start tracking a job, optionally leaving it unassigned.

    Args:
        project_name (str, optional): The name of the project. Defaults to None.
        job_name (str, optional): The name of the job. Defaults to None.

    Returns:
        int: The ID of the newly created log entry.

    Raises:
        ValueError: If a job is already running, or if the project/job names are
            not found.
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # Check if already running
        cursor.execute("SELECT id FROM logs WHERE end_time IS NULL")
        if cursor.fetchone():
            raise ValueError("A job is already running! Please stop it first.")

        p_id = None
        j_id = None

        if project_name and job_name:
            # Find project and job IDs
            cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
            p_res = cursor.fetchone()
            if not p_res:
                raise ValueError(f"Project '{project_name}' not found.")
            p_id = p_res["id"]

            cursor.execute(
                "SELECT id FROM jobs WHERE name = ? AND project_id = ?",
                (job_name, p_id),
            )
            j_res = cursor.fetchone()
            if not j_res:
                raise ValueError(
                    f"Job '{job_name}' not found in project '{project_name}'."
                )
            j_id = j_res["id"]

        now = datetime.now().replace(microsecond=0).isoformat()
        cursor.execute(
            "INSERT INTO logs (project_id, job_id, start_time) VALUES (?, ?, ?)",
            (p_id, j_id, now),
        )
        conn.commit()
        return cursor.lastrowid


def stop_log():
    """Stop tracking the currently running job.

    Returns:
        int: The ID of the stopped log entry.

    Raises:
        ValueError: If no running jobs are found.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM logs WHERE end_time IS NULL "
            "ORDER BY start_time DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("No running jobs found.")

        now = datetime.now().replace(microsecond=0).isoformat()
        cursor.execute("UPDATE logs SET end_time = ? WHERE id = ?", (now, row["id"]))
        conn.commit()
        return row["id"]


def assign_log(log_id: int, project_name: str, job_name: str):
    """Assign an existing log to a specific project and job.

    Args:
        log_id (int): The ID of the log entry.
        project_name (str): The target project name.
        job_name (str): The target job name.

    Returns:
        int: The ID of the assigned log entry.

    Raises:
        ValueError: If the log ID, project name, or job name is not found.
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # Check if log exists
        cursor.execute("SELECT id FROM logs WHERE id = ?", (log_id,))
        if not cursor.fetchone():
            raise ValueError(f"Log ID {log_id} not found.")

        # Find project and job IDs
        cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
        p_res = cursor.fetchone()
        if not p_res:
            raise ValueError(f"Project '{project_name}' not found.")
        p_id = p_res["id"]

        cursor.execute(
            "SELECT id FROM jobs WHERE name = ? AND project_id = ?", (job_name, p_id)
        )
        j_res = cursor.fetchone()
        if not j_res:
            raise ValueError(f"Job '{job_name}' not found in project '{project_name}'.")
        j_id = j_res["id"]

        cursor.execute(
            "UPDATE logs SET project_id = ?, job_id = ? WHERE id = ?",
            (p_id, j_id, log_id),
        )
        conn.commit()
        return log_id


def create_empty_log() -> int:
    """Create a new unassigned log entry with current time for both start and end.

    Returns:
        int: The ID of the newly created log entry.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now().replace(microsecond=0).isoformat()
        cursor.execute(
            "INSERT INTO logs (start_time, end_time) VALUES (?, ?)",
            (now, now),
        )
        conn.commit()
        return cursor.lastrowid


# Sentinel for optional arguments in update_log
class _MissingType:
    def __repr__(self):
        return "MISSING"


MISSING = _MissingType()


def update_log(
    log_id: int,
    project_name: str | None = MISSING,
    job_name: str | None = MISSING,
    start_time: str | None = MISSING,
    end_time: str | None = MISSING,
    memo: str | None = MISSING,
    duration_hours: float | None = MISSING,
) -> None:
    """Update an existing log entry's details. Omitted fields remain unchanged.

    Args:
        log_id (int): The ID of the log to update.
        project_name (str | None, optional): New project name or None to unassign.
        job_name (str | None, optional): New job name or None to unassign.
        start_time (str | None, optional): New ISO start time string.
        end_time (str | None, optional): New ISO end time string.
        memo (str | None, optional): New memo string.
        duration_hours (float | None, optional): New manual duration in hours.

    Raises:
        ValueError: If the log ID is not found, or if date/time logic is violated.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM logs WHERE id = ?", (log_id,))
        existing = cursor.fetchone()
        if not existing:
            raise ValueError(f"Log ID {log_id} not found.")

        # Resolve IDs for project/job names
        p_id = existing["project_id"]
        j_id = existing["job_id"]

        # If both project_name and job_name are explicitly provided, resolve IDs
        if project_name is not MISSING and job_name is not MISSING:
            if project_name is None or job_name is None:
                p_id = None
                j_id = None
            else:
                # Logic to find p_id and j_id from names
                cursor.execute(
                    "SELECT id FROM projects WHERE name = ?", (project_name,)
                )
                p_res = cursor.fetchone()
                if p_res:
                    p_id = p_res["id"]
                    cursor.execute(
                        "SELECT id FROM jobs WHERE name = ? AND project_id = ?",
                        (job_name, p_id),
                    )
                    j_res = cursor.fetchone()
                    if j_res:
                        j_id = j_res["id"]
                    else:
                        raise ValueError(
                            f"Job '{job_name}' not found under '{project_name}'"
                        )
                else:
                    raise ValueError(f"Project '{project_name}' not found")

        # Merge values
        final_start = (
            start_time if start_time is not MISSING else existing["start_time"]
        )
        final_end = end_time if end_time is not MISSING else existing["end_time"]
        final_memo = memo if memo is not MISSING else existing["memo"]
        final_duration = (
            duration_hours
            if duration_hours is not MISSING
            else existing["duration_hours"]
        )

        # Validation
        try:
            if final_start is None:
                raise ValueError("Start time cannot be None.")
            s_dt = datetime.fromisoformat(final_start)
            if final_end:
                e_dt = datetime.fromisoformat(final_end)
                if e_dt < s_dt:
                    raise ValueError("End time cannot be before start time.")
        except ValueError as e:
            raise ValueError(f"Invalid date/time format or value: {e}") from e

        cursor.execute(
            """
            UPDATE logs
            SET project_id = ?, job_id = ?, start_time = ?, end_time = ?,
                memo = ?, duration_hours = ?
            WHERE id = ?
            """,
            (p_id, j_id, final_start, final_end, final_memo, final_duration, log_id),
        )
        conn.commit()


def delete_log(log_id: int) -> None:
    """Delete a specific log entry by its ID.

    Args:
        log_id (int): The ID of the log entry to delete.

    Raises:
        ValueError: If the log ID is not found.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM logs WHERE id = ?", (log_id,))
        if cursor.rowcount == 0:
            raise ValueError(f"Log ID {log_id} not found.")
        conn.commit()


def list_logs():
    """List all tracked time logs.

    Returns:
        list[sqlite3.Row]: A list of log records with joined project and job details.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT logs.id, projects.name as project_name, jobs.name as job_name,
                   jobs.code as job_code,
                   logs.start_time, logs.end_time, logs.memo, logs.duration_hours
            FROM logs
            LEFT JOIN projects ON logs.project_id = projects.id
            LEFT JOIN jobs ON logs.job_id = jobs.id
            ORDER BY logs.start_time DESC
        """)
        return cursor.fetchall()


def create_assigned_log(project_name: str, job_name: str) -> int:
    """Create a new log entry pre-assigned to the project and job.

    Args:
        project_name (str): The name of the project.
        job_name (str): The name of the job.

    Returns:
        int: The ID of the newly created log entry.

    Raises:
        ValueError: If the project or job name is not found.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
        p_res = cursor.fetchone()
        if not p_res:
            raise ValueError(f"Project '{project_name}' not found.")
        p_id = p_res["id"]

        cursor.execute(
            "SELECT id FROM jobs WHERE name = ? AND project_id = ?",
            (job_name, p_id),
        )
        j_res = cursor.fetchone()
        if not j_res:
            raise ValueError(f"Job '{job_name}' not found in project '{project_name}'.")
        j_id = j_res["id"]

        now = datetime.now().replace(microsecond=0).isoformat()
        cursor.execute(
            "INSERT INTO logs (project_id, job_id, start_time, end_time, "
            "duration_hours) VALUES (?, ?, ?, ?, ?)",
            (p_id, j_id, now, now, None),
        )
        conn.commit()
        return cursor.lastrowid


def update_job(
    project_name: str,
    job_name: str,
    description: str | None = MISSING,
    code: str | None = MISSING,
) -> None:
    """Update an existing job's details. Job name is immutable here.

    Args:
        project_name (str): The project name.
        job_name (str): The job name to update.
        description (str | None, optional): New description.
        code (str | None, optional): New job code.

    Raises:
        ValueError: If the job is not found.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT jobs.id, jobs.description, jobs.code
            FROM jobs
            JOIN projects ON jobs.project_id = projects.id
            WHERE projects.name = ? AND jobs.name = ?
        """,
            (project_name, job_name),
        )
        existing = cursor.fetchone()
        if not existing:
            raise ValueError(f"Job '{job_name}' in project '{project_name}' not found.")

        final_description = (
            description if description is not MISSING else existing["description"]
        )
        final_code = code if code is not MISSING else existing["code"]

        cursor.execute(
            "UPDATE jobs SET description = ?, code = ? WHERE id = ?",
            (final_description, final_code, existing["id"]),
        )
        conn.commit()
