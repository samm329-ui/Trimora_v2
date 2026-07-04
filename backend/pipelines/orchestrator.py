from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict

from backend.models.job import JobStatus
from backend.pipelines.production_pipeline import ProductionPipeline
from backend.storage.job_store import JobStore
from backend.execution.engine import ExecutionEngine


class Orchestrator:
    def __init__(self, job_store: JobStore, engine: ExecutionEngine | None = None):
        self.job_store = job_store
        self.pipeline = ProductionPipeline(job_store, engine=engine)
        self._tasks: Dict[str, asyncio.Task] = {}

    async def start_job(self, job_id: str) -> None:
        if job_id in self._tasks and not self._tasks[job_id].done():
            return
        self.job_store.set_status(job_id, JobStatus.queued, 0.01)
        self._tasks[job_id] = asyncio.create_task(self._run(job_id))

    async def _run(self, job_id: str) -> None:
        try:
            await self.pipeline.run(job_id)
        except asyncio.CancelledError:
            self.job_store.set_status(job_id, JobStatus.cancelled, 0.0, error="Job cancelled")
            raise
        except Exception as exc:
            self.job_store.set_status(job_id, JobStatus.failed, 0.0, error=str(exc))

    def cancel_job(self, job_id: str) -> None:
        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            self.job_store.update_job(job_id, cancelled=True)

    async def retry_job(self, job_id: str) -> None:
        job = self.job_store.load_job(job_id)
        self.job_store.update_job(job_id, retries=job.retries + 1, cancelled=False, error=None)
        await self.start_job(job_id)
