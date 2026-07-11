"""Controller for WTL desktop widget, handling state updates via CLI stream."""

import asyncio
import json
import os
import sys
from datetime import datetime


class TaskController:
    """Controls the lifecycle and business logic of the WTL desktop widget."""

    def __init__(self):
        self.is_monitoring = False
        self.process = None

    def start_monitoring(self, page, ui_component):
        """Starts the background task to poll the CLI and update the UI."""
        if self.is_monitoring:
            return
        self.is_monitoring = True

        # Run async loop inside Flet's event loop
        page.run_task(self._monitoring_loop, page, ui_component)

    async def _monitoring_loop(self, page, ui_component):
        """Asynchronous loop that reads CLI stream to update UI."""
        cmd_args = ["status", "--watch", "--json"]

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            self.process = await asyncio.create_subprocess_exec(
                "wtl",
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=sys.stderr,
                env=env,
            )
        except FileNotFoundError:
            # Fallback to python execution with unbuffered flag -u
            python_cmd = [
                sys.executable,
                "-u",
                "-c",
                "from work_time_logger.cli import app; app()",
            ]
            try:
                self.process = await asyncio.create_subprocess_exec(
                    python_cmd[0],
                    *(python_cmd[1:] + cmd_args),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=sys.stderr,
                    env=env,
                )
            except Exception as e:
                print(f"Failed to start wtl process: {e}")
                ui_component.update_state(is_running=False)
                ui_component.update()
                page.update()
                self.is_monitoring = False
                return

        try:
            # Read stdout line by line
            while self.is_monitoring and self.process.stdout:
                line = await self.process.stdout.readline()
                if not line:
                    break

                output = line.decode("utf-8", errors="replace").strip()
                try:
                    active_jobs = json.loads(output) if output else []
                except json.JSONDecodeError:
                    continue

                if active_jobs:
                    job = active_jobs[0]
                    project = job.get("project_name")
                    job_name = job.get("job_name")
                    start_time_str = job.get("start_time")

                    # Re-calculate elapsed time locally
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

                ui_component.update()
                page.update()

        except Exception as e:
            print(f"Error in monitoring loop: {e}")
        finally:
            self.is_monitoring = False
            if self.process:
                try:
                    self.process.terminate()
                    await self.process.wait()
                except Exception:
                    pass
