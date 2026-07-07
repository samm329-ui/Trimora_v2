from __future__ import annotations

import asyncio
import itertools
import logging

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
        self._sequence_counter = itertools.count()

    async def start(self, num_workers: int = 1) -> None:
        """Start worker loops."""
        self._running = True
        self._workers = [
            asyncio.create_task(self._worker_loop(i))
            for i in range(num_workers)
        ]
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("LLMScheduler started with %d workers", num_workers)

    async def stop(self) -> None:
        """Stop all workers and drain the queue."""
        self._running = False
        if hasattr(self, "_heartbeat_task"):
            self._heartbeat_task.cancel()
            await asyncio.gather(self._heartbeat_task, return_exceptions=True)
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        remaining = self._queue.qsize()
        self._workers.clear()
        if remaining > 0:
            logger.warning(
                "Scheduler stopped with %d queued tasks discarded", remaining
            )
        else:
            logger.info("LLMScheduler stopped")

    def submit(self, task: LLMTask) -> LLMExecutionHandle:
        """Submit task to queue. Task must already be validated and split.

        Never raises — always returns a handle. If enqueueing fails,
        the handle's future is set with the exception so callers can
        await it safely via asyncio.gather(return_exceptions=True).
        """
        handle = LLMExecutionHandle(task)
        try:
            task.transition(TaskState.QUEUED)
            seq = next(self._sequence_counter)
            self._queue.put_nowait((
                task.priority.value,
                task.created_at,
                seq,
                task,
                handle,
            ))
            self._metrics.record_submission(task)
            self._metrics.record_queue_depth(self._queue.qsize())
        except Exception as e:
            logger.exception("Failed to enqueue task %s", task.task_id)
            task.transition(TaskState.FAILED)
            handle.set_error(e)
            self._metrics.record_error(task, e)
        return handle

    async def _worker_loop(self, worker_id: int) -> None:
        """Process tasks from queue. Never exits unless cancelled."""
        self._metrics.active_workers += 1
        logger.info("Worker %d started", worker_id)
        try:
            while self._running:
                task = None
                handle = None
                dequeued = False
                try:
                    raw = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                    dequeued = True
                    priority, ts, seq, task, handle = raw

                    result = await self.adapter.execute(task)
                    handle.set_result(result)
                    self._metrics.record_completion(task, result)

                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    if dequeued:
                        self._queue.task_done()
                        dequeued = False
                    break
                except Exception as e:
                    self._metrics.worker_exceptions += 1
                    logger.exception(
                        "Worker %d failed while executing task %s",
                        worker_id,
                        task.task_id if task else "<unknown>",
                    )
                    if handle is not None and not handle.done():
                        try:
                            handle.set_error(e)
                        except Exception:
                            pass
                    try:
                        self._metrics.record_error(task, e)
                    except Exception:
                        pass
                finally:
                    if dequeued:
                        self._queue.task_done()
        finally:
            self._metrics.active_workers -= 1
            logger.info("Worker %d stopped", worker_id)
            if (
                self._metrics.active_workers == 0
                and self._running
                and self._queue.qsize() > 0
            ):
                logger.critical(
                    "SCHEDULER OUTAGE: 0 active workers, %d tasks queued",
                    self._queue.qsize(),
                )

    async def _heartbeat_loop(self, interval: float = 30.0) -> None:
        """Log scheduler state periodically for long-running jobs."""
        while self._running:
            await asyncio.sleep(interval)
            if self._running:
                logger.info(
                    "Scheduler heartbeat — workers: %d, queue: %d, "
                    "completed: %d, failed: %d, exceptions: %d",
                    self._metrics.active_workers,
                    self._queue.qsize(),
                    self._metrics.completed,
                    self._metrics.failed,
                    self._metrics.worker_exceptions,
                )

    @property
    def metrics(self) -> SchedulerMetrics:
        return self._metrics
