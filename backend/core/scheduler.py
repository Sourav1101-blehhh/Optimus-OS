"""
scheduler.py — Optimus Proactive Automation Daemon v5.0
=========================================================
Spin up persistently on server init. Queries a persistent state matrix
('data/cron_jobs.json') every 60 seconds to execute automated system evaluation
checks, routine tasks, and push unprompted alerts downstream to the client interface.
"""
import asyncio
import json
import logging
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger("OptimusScheduler")

class ProactiveScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.jobs_file = os.path.join(os.path.dirname(__file__), "..", "..", "data", "cron_jobs.json")
        # Ensure data directory exists
        os.makedirs(os.path.dirname(self.jobs_file), exist_ok=True)
        self._init_jobs_file()

    def _init_jobs_file(self):
        if not os.path.exists(self.jobs_file):
            default_jobs = [
                {
                    "id": "system_health_check",
                    "interval_seconds": 3600,
                    "action": "system_vitals",
                    "enabled": True
                }
            ]
            with open(self.jobs_file, "w") as f:
                json.dump(default_jobs, f, indent=4)

    async def _execute_job(self, job_def: dict):
        """
        Dynamically executes a plugin based on cron definitions.
        If it yields an alert, broadcasts it to all active websockets.
        """
        if not job_def.get("enabled", False):
            return

        action = job_def.get("action")
        logger.info(f"Proactive Scheduler: Executing routine task '{job_def.get('id')}' -> plugin: {action}")
        
        from backend.core.plugin_manager import plugin_manager
        from backend.main import manager # Circular import guard
        
        # In a real environment, we would pass specific args. Here we pass a generic check intent.
        try:
            result = await plugin_manager.execute_async(action, {"command": "Proactive automated check", "query": "", "_approved": True})
            
            # If the result suggests a critical state (e.g. CPU > 90%), we push an unprompted alert.
            # Here we just blindly broadcast for demonstration of the unprompted alert channel.
            if "alert" in result.lower() or "critical" in result.lower() or True:
                payload = {
                    "type": "chat",
                    "data": f"[PROACTIVE ALERT] Routine '{job_def.get('id')}' executed.\n\n{result}"
                }
                await manager.broadcast(payload)
                
        except Exception as e:
            logger.error(f"Proactive job '{job_def.get('id')}' failed: {e}")

    def sync_jobs_from_disk(self):
        """Reads cron_jobs.json and syncs them into APScheduler."""
        try:
            with open(self.jobs_file, "r") as f:
                jobs = json.load(f)
                
            # Clear existing jobs
            self.scheduler.remove_all_jobs()
            
            for job in jobs:
                if job.get("enabled", False):
                    # We schedule a wrapper coroutine
                    async def wrapper(j=job):
                        await self._execute_job(j)
                        
                    self.scheduler.add_job(
                        wrapper,
                        trigger=IntervalTrigger(seconds=job.get("interval_seconds", 60)),
                        id=job.get("id"),
                        replace_existing=True
                    )
            logger.info(f"Proactive Scheduler synchronized {len(self.scheduler.get_jobs())} active routines.")
        except Exception as e:
            logger.error(f"Failed to sync jobs from disk: {e}")

    async def poll_matrix_loop(self):
        """Background task that checks the JSON matrix for changes every 60s."""
        while True:
            self.sync_jobs_from_disk()
            await asyncio.sleep(60)

    def start(self):
        self.scheduler.start()
        self.sync_jobs_from_disk()
        asyncio.create_task(self.poll_matrix_loop(), name="scheduler_poll")

optimus_scheduler = ProactiveScheduler()
