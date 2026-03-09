"""Core business logic and database operations for Work Time Logger."""

import csv
from datetime import datetime

from .db import get_connection, init_db


def setup():
    """Initialize the database configuration and tables."""
    init_db()


def add_project(name: str):
    """Add a new project to the database."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO projects (name) VALUES (?)", (name,))
        conn.commit()
        return cursor.lastrowid


def list_projects():
    """List all projects in the database."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM projects")
        return cursor.fetchall()


def delete_project(project_id: int):
    """Delete a project by its ID, cascading deletes to its jobs and logs."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()


def add_job(name: str, project_name: str, description: str = "", code: str = None):
    """Add a new job under a specific project."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
        result = cursor.fetchone()
        if not result:
            raise ValueError(f"Project '{project_name}' not found.")
        project_id = result["id"]
        cursor.execute(
            "INSERT INTO jobs (project_id, name, description, code) VALUES (?, ?, ?, ?)",
            (project_id, name, description, code),
        )
        conn.commit()
        return cursor.lastrowid


def list_jobs(project_name: str = None):
    """List all jobs, optionally filtering by project name."""
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
    """Delete a job by its ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        if cursor.rowcount == 0:
            raise ValueError(f"Job ID {job_id} not found.")
        conn.commit()


def import_jobs_from_csv(filepath: str, project_name: str, profile_path: str = None) -> int:
    """Import jobs from a CSV file into a given project."""
    import os
    import tomllib

    mapping = {
        "name": "{name}",
        "description": "{description}",
        "code": "{code}"
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
        except Exception:
            pass

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
        result = cursor.fetchone()
        if not result:
            raise ValueError(f"Project '{project_name}' not found.")
        project_id = result["id"]

        with open(filepath, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                def format_field(template):
                    if not template:
                        return None
                    try:
                        return template.format(**row)
                    except KeyError:
                        return None

                name = format_field(mapping["name"])
                if not name and "name" in row:
                    name = row["name"]
                
                if not name:
                    continue

                description = format_field(mapping["description"])
                if description is None:
                    description = row.get("description", "")

                code = format_field(mapping["code"])
                if code is None:
                    code = row.get("code")

                try:
                    cursor.execute(
                        "INSERT INTO jobs (project_id, name, description, code) "
                        "VALUES (?, ?, ?, ?)",
                        (project_id, name, description, code),
                    )
                    count += 1
                except Exception:
                    pass
        conn.commit()
        return count


def start_log(project_name: str = None, job_name: str = None):
    """Start tracking a job, optionally leaving it unassigned."""
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
    """Stop tracking the currently running job."""
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
    """Assign an existing log to a specific project and job."""
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
    """Create a new unassigned log entry with current time for both start and end."""
    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now().replace(microsecond=0).isoformat()
        cursor.execute(
            "INSERT INTO logs (start_time, end_time) VALUES (?, ?)",
            (now, now),
        )
        conn.commit()
        return cursor.lastrowid


def update_log(
    log_id: int,
    project_name: str | None,
    job_name: str | None,
    start_time: str,
    end_time: str | None,
    memo: str,
) -> None:
    """Update an existing log entry's details."""
    with get_connection() as conn:
        cursor = conn.cursor()

        p_id = None
        j_id = None

        if project_name and job_name:
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

        cursor.execute(
            """
            UPDATE logs
            SET project_id = ?, job_id = ?, start_time = ?, end_time = ?, memo = ?
            WHERE id = ?
            """,
            (p_id, j_id, start_time, end_time, memo, log_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Log ID {log_id} not found.")
        conn.commit()


def delete_log(log_id: int) -> None:
    """Delete a specific log entry by its ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM logs WHERE id = ?", (log_id,))
        if cursor.rowcount == 0:
            raise ValueError(f"Log ID {log_id} not found.")
        conn.commit()


def list_logs():
    """List all tracked time logs."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT logs.id, projects.name as project_name, jobs.name as job_name,
                   jobs.code as job_code,
                   logs.start_time, logs.end_time, logs.memo
            FROM logs
            LEFT JOIN projects ON logs.project_id = projects.id
            LEFT JOIN jobs ON logs.job_id = jobs.id
            ORDER BY logs.start_time DESC
        """)
        return cursor.fetchall()
