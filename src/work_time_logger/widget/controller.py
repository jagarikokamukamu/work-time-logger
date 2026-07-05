"""Controller for WTL desktop widget, handling DB polling and state updates."""

import asyncio
import json
import subprocess
import sys
import time
from datetime import datetime


class TaskController:
    """Controls the lifecycle and business logic of the WTL desktop widget."""

    def __init__(self):
        self.is_monitoring = False

    def _run_wtl_command(self, args: list[str]) -> str:
        """Run wtl command and return stdout.

        If 'wtl' is not in path, falls back to using sys.executable.
        """
        # 1. Try 'wtl' command directly
        try:
            res = subprocess.run(
                ["wtl"] + args, capture_output=True, text=True, check=True
            )
            return res.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        # 2. Fallback to module execution in dev environments
        try:
            cmd = [sys.executable, "-c", "from work_time_logger.cli import app; app()"]
            res = subprocess.run(cmd + args, capture_output=True, text=True, check=True)
            return res.stdout.strip()
        except Exception as e:
            print(f"Failed to execute wtl command: {e}")
            return ""

    def start_monitoring(self, page, ui_component):
        """Starts the background task to poll the CLI and update the UI."""
        if self.is_monitoring:
            return
        self.is_monitoring = True

        # Run async loop inside Flet's event loop
        page.run_task(self._monitoring_loop, page, ui_component)

    async def _monitoring_loop(self, page, ui_component):
        """Asynchronous loop that polls status and updates UI every second."""
        last_sync_time = 0.0
        active_jobs = []
        loop = asyncio.get_running_loop()

        while self.is_monitoring:
            try:
                current_time = time.time()

                # Poll status every 3 seconds off the main event loop
                if current_time - last_sync_time >= 3.0:
                    output = await loop.run_in_executor(
                        None, self._run_wtl_command, ["status", "--json"]
                    )
                    active_jobs = json.loads(output) if output else []
                    last_sync_time = current_time

                if active_jobs:
                    job = active_jobs[0]
                    project = job.get("project_name")
                    job_name = job.get("job_name")
                    start_time_str = job.get("start_time")

                    # Re-calculate elapsed time locally every second
                    start_dt = datetime.fromisoformat(start_time_str)
                    elapsed = datetime.now() - start_dt
                    secs = int(elapsed.total_seconds())

                    hours = secs // 3600
                    minutes = (secs % 3600) // 60
                    seconds = secs % 60
                    time_str = f"{hours:02}:{minutes:02}:{seconds:02}"

                    p_disp = project or "[Unassigned]"
                    j_disp = job_name or "[Unassigned]"

                    ui_component.update_state(
                        is_running=True,
                        job_name=f"{p_disp} / {j_disp}",
                        time_str=time_str,
                    )
                else:
                    ui_component.update_state(is_running=False)

                # Force update the component and wait for render
                ui_component.update()
                page.update()
            except Exception as e:
                print(f"Error in monitoring loop: {e}")

            await asyncio.sleep(1)
