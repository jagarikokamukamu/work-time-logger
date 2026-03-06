from .db import init_db, get_connection
import csv
from datetime import datetime
from typing import Optional

def setup():
    init_db()

def add_project(name: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO projects (name) VALUES (?)", (name,))
        conn.commit()
        return cursor.lastrowid

def list_projects():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM projects")
        return cursor.fetchall()

def delete_project(project_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()

def add_job(name: str, project_name: str, description: str = ""):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
        result = cursor.fetchone()
        if not result:
            raise ValueError(f"Project '{project_name}' not found.")
        project_id = result['id']
        cursor.execute("INSERT INTO jobs (project_id, name, description) VALUES (?, ?, ?)", 
                       (project_id, name, description))
        conn.commit()
        return cursor.lastrowid

def list_jobs(project_name: str = None):
    with get_connection() as conn:
        cursor = conn.cursor()
        if project_name:
            cursor.execute('''
                SELECT jobs.*, projects.name as project_name 
                FROM jobs 
                JOIN projects ON jobs.project_id = projects.id 
                WHERE projects.name = ?
            ''', (project_name,))
        else:
            cursor.execute('''
                SELECT jobs.*, projects.name as project_name 
                FROM jobs 
                JOIN projects ON jobs.project_id = projects.id
            ''')
        return cursor.fetchall()

def import_jobs_from_csv(filepath: str, project_name: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
        result = cursor.fetchone()
        if not result:
            raise ValueError(f"Project '{project_name}' not found.")
        project_id = result['id']

        with open(filepath, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                name = row.get('name')
                description = row.get('description', '')
                if name:
                    try:
                        cursor.execute("INSERT INTO jobs (project_id, name, description) VALUES (?, ?, ?)", 
                                       (project_id, name, description))
                        count += 1
                    except Exception as e:
                        pass
        conn.commit()
        return count

def start_log(project_name: str, job_name: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Check if already running
        cursor.execute("SELECT id FROM logs WHERE end_time IS NULL")
        if cursor.fetchone():
            raise ValueError("A job is already running! Please stop it first.")

        # Find project and job IDs
        cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
        p_res = cursor.fetchone()
        if not p_res: raise ValueError(f"Project '{project_name}' not found.")
        
        cursor.execute("SELECT id FROM jobs WHERE name = ? AND project_id = ?", (job_name, p_res['id']))
        j_res = cursor.fetchone()
        if not j_res: raise ValueError(f"Job '{job_name}' not found in project '{project_name}'.")

        now = datetime.now().isoformat()
        cursor.execute("INSERT INTO logs (project_id, job_id, start_time) VALUES (?, ?, ?)", 
                       (p_res['id'], j_res['id'], now))
        conn.commit()
        return cursor.lastrowid

def stop_log():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM logs WHERE end_time IS NULL ORDER BY start_time DESC LIMIT 1")
        row = cursor.fetchone()
        if not row:
            raise ValueError("No running jobs found.")
            
        now = datetime.now().isoformat()
        cursor.execute("UPDATE logs SET end_time = ? WHERE id = ?", (now, row['id']))
        conn.commit()
        return row['id']

def list_logs():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT logs.id, projects.name as project_name, jobs.name as job_name, 
                   logs.start_time, logs.end_time, logs.memo
            FROM logs 
            JOIN projects ON logs.project_id = projects.id
            JOIN jobs ON logs.job_id = jobs.id
            ORDER BY logs.start_time DESC
        ''')
        return cursor.fetchall()
