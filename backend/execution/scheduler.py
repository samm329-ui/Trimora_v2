from __future__ import annotations

import asyncio
import logging
import time

from backend.execution.models import (
    LLMExecutionHandle,
    LLMExecutionResult,
    LLMTask,
    SchedulerMetrics,
    TaskState,
)
from backend.execution.provider_adapter import ProviderAdapter

logger = logging.getLogger(__name__)


class LLMScheduler:
    """Minimal scheduler — queue and dispatch only.

    Does NOT resolve prompts, build payloads, or contain business logic.
    """

    def __init__(self, provider_adapter: ProviderAdapter):
        self.adapter = provider_adapter
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._workers: list[asyncio.Task] = []
        self._running = False
        self._metrics = SchedulerMetrics()

    async def start(self, num_workers: int = 1) -> None:
        """Start worker loops."""
        self._running = True
        self._workers = [
            asyncio.create_task(self._worker_loop(i))
            for i in range(num_workers)
        ]
        logger.info("LLMScheduler started with %d workers", num_workers)

    async def stop(self) -> None:
        """Stop all workers and drain the queue."""
        self._running = False
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("LLMScheduler stopped")

    def submit(self, task: LLMTask) -> LLMExecutionHandle:
        """Submit task to queue. Task must already be validated and split."""
        handle = LLMExecutionHandle(task)
        task.transition(TaskState.QUEUED)

        self._queue.put_nowait((
            task.priority.value,
            task.created_at,
            task.estimated_total_tokens,
            task,
            handle,
        ))

        self._metrics.record_submission(task)
        return handle

    async def _worker_loop(self, worker_id: int) -> None:
        """Process tasks from queue."""
        while self._running:
            try:
                priority, ts, est_tokens, task, handle = (
                    await asyncio.wait_for(self._queue.get(), timeout=1.0)
                )

                result = await self.adapter.execute(task)
                handle.set_result(result)
                self._metrics.record_completion(task, result)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("LLMScheduler worker %d error: %s", worker_id, e)
                try:
                    handle.set_error(e)
                except Exception:
                    pass
                self._metrics.record_error(task, e)

    @property
    def metrics(self) -> SchedulerMetrics:
        return self._metrics
