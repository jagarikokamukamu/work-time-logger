"""Command-line interface commands for Work Time Logger."""

import typer
from rich.console import Console
from rich.table import Table

from . import db, operations

app = typer.Typer(help="Work Time Logger (wtl)", no_args_is_help=True)
console = Console()

project_app = typer.Typer(help="Manage projects")
app.add_typer(project_app, name="project")

job_app = typer.Typer(help="Manage jobs")
app.add_typer(job_app, name="job")

log_app = typer.Typer(help="Manage logs")
app.add_typer(log_app, name="log")


# --- Autocompletion Functions ---
def complete_project_name(incomplete: str):
    """Provide Typer autocompletion for project names."""
    projects = operations.list_projects()
    for p in projects:
        if p["name"].startswith(incomplete):
            yield p["name"]


def complete_job_name(ctx: typer.Context, incomplete: str):
    """Provide Typer autocompletion for job names."""
    project_name = None
    # Typer Context hack: check if --to or -t or project name was passed before
    for k, v in ctx.params.items():
        if k in ("project_name", "project") and v:
            project_name = v
            break

    jobs = operations.list_jobs(project_name=project_name)
    for j in jobs:
        if j["name"].startswith(incomplete):
            yield j["name"]


# --- Main Commands ---


@app.command("start")
def start(
    project_name: str = typer.Option(
        None, "--project", "-p", help="Name of the project", autocompletion=complete_project_name
    ),
    job_name: str = typer.Option(
        None, "--job", "-j", help="Name of the job", autocompletion=complete_job_name
    ),
    unassigned: bool = typer.Option(
        False, "--unassigned", "-u", help="Start an unassigned timer"
    ),
):
    """Start tracking a job."""
    if not unassigned and (not project_name or not job_name):
        console.print(
            "[red]Error: You must provide a project and job name, "
            "or use the --unassigned flag.[/red]"
        )
        raise typer.Exit(1)

    try:
        p_name = None if unassigned else project_name
        j_name = None if unassigned else job_name
        operations.start_log(p_name, j_name)

        if unassigned:
            console.print(
                "[green]Started tracking an [bold]unassigned[/bold] job.[/green]"
            )
        else:
            console.print(
                f"[green]Started tracking '{job_name}' in '{project_name}'.[/green]"
            )
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@app.command("stop")
def stop():
    """Stop the current tracking job."""
    try:
        operations.stop_log()
        console.print("[green]Stopped current job tracking![/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


# --- Project Commands ---


@project_app.command("add")
def add_project(
    name: str = typer.Option(..., "--project", "-p", help="Name of the project"),
):
    """Add a new project."""
    try:
        pid = operations.add_project(name)
        console.print(f"[green]Added project '{name}' with ID {pid}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@project_app.command("list")
def list_projects():
    """List all projects."""
    projects = operations.list_projects()
    table = Table("ID", "Project Name")
    for p in projects:
        table.add_row(str(p["id"]), p["name"])
    console.print(table)


@project_app.command("delete")
def delete_project(project_id: int):
    """Delete a project by ID."""
    try:
        operations.delete_project(project_id)
        console.print(f"[green]Deleted project ID {project_id}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


# --- Job Commands ---


@job_app.command("add")
def add_job(
    name: str = typer.Option(..., "--job", "-j", help="Name of the job"),
    project_name: str = typer.Option(
        ...,
        "--project",
        "-p",
        help="Project to add the job to",
        autocompletion=complete_project_name,
    ),
    code: str = typer.Option(
        None, "--code", "-c", help="Optional external code for export features (e.g. JTC format code)"
    ),
):
    """Add a new job to a project."""
    try:
        jid = operations.add_job(name, project_name, code=code)
        console.print(
            f"[green]Added job '{name}' to project '{project_name}' "
            f"with ID {jid}[/green]"
        )
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@job_app.command("list")
def list_jobs(
    project_name: str = typer.Option(
        None,
        "--project",
        "-p",
        help="Filter by project name",
        autocompletion=complete_project_name,
    ),
):
    """List jobs."""
    jobs = operations.list_jobs(project_name)
    table = Table("ID", "Job Name", "Project")
    for j in jobs:
        table.add_row(str(j["id"]), j["name"], j["project_name"])
    console.print(table)


@job_app.command("delete")
def delete_job(
    name: str = typer.Option(..., "--job", "-j", help="Name of the job"),
    project_name: str = typer.Option(
        ...,
        "--project",
        "-p",
        help="Project the job belongs to",
        autocompletion=complete_project_name,
    ),
):
    """Delete a job from a project."""
    try:
        jobs = operations.list_jobs(project_name)
        job_to_delete = next((j for j in jobs if j["name"] == name), None)
        if not job_to_delete:
            console.print(f"[red]Error: Job '{name}' not found in '{project_name}'.[/red]")
            return
        
        operations.delete_job(job_to_delete["id"])
        console.print(f"[green]Deleted job '{name}' from '{project_name}'[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@job_app.command("import")
def import_jobs(
    filepath: str = typer.Argument(..., help="Path to the CSV file"),
    project_name: str = typer.Option(
        ...,
        "--project",
        "-p",
        help="Project to add these jobs to",
        autocompletion=complete_project_name,
    ),
    profile: str = typer.Option(
        str(db.DB_DIR / "profile.toml"),
        "--profile",
        "-r",
        help="Path to the TOML profile for import mapping",
    ),
):
    """Import jobs from a CSV file."""
    try:
        count = operations.import_jobs_from_csv(filepath, project_name, profile_path=profile)
        console.print(f"[green]Imported {count} jobs into '{project_name}'.[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@log_app.command("delete")
def delete_log(log_id: int = typer.Argument(..., help="ID of the log to delete")):
    """Delete a log entry."""
    try:
        operations.delete_log(log_id)
        console.print(f"[green]Deleted log {log_id}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


# --- Log Commands ---


@log_app.command("assign")
def assign(
    log_id: int = typer.Argument(..., help="ID of the log to edit"),
    project_name: str = typer.Option(
        ..., "--project", "-p", help="Name of the project", autocompletion=complete_project_name
    ),
    job_name: str = typer.Option(
        ..., "--job", "-j", help="Name of the job", autocompletion=complete_job_name
    ),
):
    """Assign a project and job to an existing log."""
    try:
        operations.assign_log(log_id, project_name, job_name)
        console.print(
            f"[green]Successfully assigned Log ID {log_id} to "
            f"'{job_name}' in '{project_name}'.[/green]"
        )
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@log_app.command("list")
def list_logs():
    """List logs."""
    logs = operations.list_logs()
    table = Table("ID", "Project", "Job", "Job Code", "Start Time", "End Time", "Memo")
    for log_entry in logs:
        p_name = log_entry["project_name"] or "[Unassigned]"
        j_name = log_entry["job_name"] or "[Unassigned]"
        j_code = log_entry["job_code"] or ""
        end_time = log_entry["end_time"] or "Running..."
        memo = log_entry["memo"] if log_entry["memo"] else ""
        table.add_row(
            str(log_entry["id"]),
            p_name,
            j_name,
            j_code,
            log_entry["start_time"][:19],
            end_time[:19] if end_time != "Running..." else "Running...",
            memo,
        )
    console.print(table)


@log_app.command("export")
def export_logs(
    profile: str = typer.Option(
        str(db.DB_DIR / "profile.toml"),
        "--profile",
        "-r",
        help="Path to the TOML export profile",
    ),
    out: str = typer.Option("report.csv", "--out", "-o", help="Output CSV file path"),
    date: str = typer.Option(
        None,
        "--date",
        "-d",
        help="Filter logs by date (YYYY-MM-DD). Defaults to today. Pass 'all' to export all logs.",
    ),
):
    """Export logs to a formatted CSV file based on a TOML profile."""
    import datetime as dt
    from . import exporter

    # Resolve date filter
    if date is None:
        target_date = dt.date.today().isoformat()
    elif date.lower() == "all":
        target_date = None
    else:
        target_date = date

    try:
        count = exporter.export_logs(profile, out, target_date=target_date)
        if count > 0:
            label = target_date if target_date else "all dates"
            console.print(f"[green]Successfully exported {count} grouped rows to {out} ({label})[/green]")
        else:
            console.print("[yellow]No logs matched or exported.[/yellow]")
    except Exception as e:
        console.print(f"[red]Error exporting logs: {e}[/red]")
