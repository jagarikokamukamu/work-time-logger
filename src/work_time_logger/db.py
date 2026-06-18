"""Database configuration and initialization routines for Work Time Logger.

This module handles the SQLite database setup, migrations, and provides
a thread-safe connection manager.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_DIR = Path.home() / ".wtl"
DB_PATH = DB_DIR / "db.sqlite3"


def init_db():
    """Initialize the SQLite database and create necessary tables.

    This function ensures the database directory exists and creates the
    `projects`, `jobs`, and `logs` tables if they are missing. It also
    handles basic schema migrations.
    """
    if not DB_DIR.exists():
        DB_DIR.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        cursor = conn.cursor()

        # Projects Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                is_archived INTEGER DEFAULT 0
            )
        """
        )

        # Migration: Add is_archived column if it doesn't exist
        try:
            cursor.execute("SELECT is_archived FROM projects LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute(
                "ALTER TABLE projects ADD COLUMN is_archived INTEGER DEFAULT 0"
            )

        # Jobs Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                code TEXT,
                is_favorite INTEGER DEFAULT 0,
                UNIQUE(project_id, name),
                FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
            )
        """
        )

        # Migration: Add code column if it doesn't exist
        try:
            cursor.execute("SELECT code FROM jobs LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE jobs ADD COLUMN code TEXT")

        # Migration: Add is_favorite column if it doesn't exist
        try:
            cursor.execute("SELECT is_favorite FROM jobs LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE jobs ADD COLUMN is_favorite INTEGER DEFAULT 0")

        # Logs Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                job_id INTEGER,
                start_time DATETIME NOT NULL,
                end_time DATETIME,
                memo TEXT,
                duration_hours REAL,
                FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
                FOREIGN KEY (job_id) REFERENCES jobs (id) ON DELETE CASCADE
            )
        """
        )

        # Migration: Add duration_hours column if it doesn't exist
        try:
            cursor.execute("SELECT duration_hours FROM logs LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE logs ADD COLUMN duration_hours REAL")

        conn.commit()


@contextmanager
def get_connection():
    """Get a connection to the SQLite database.

    This function is a context manager that provides a database connection
    with `sqlite3.Row` factory enabled and foreign key support turned on.
    The connection is automatically closed when the context exits.

    Yields:
        sqlite3.Connection: The established database connection.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # Enable foreign key support
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
    finally:
        conn.close()
