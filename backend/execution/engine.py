from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Awaitable

from backend.execution.models import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionHandle,
    ExecutionMetrics,
    RequestPriority,
    PipelineStage,
    RetryPolicy,
)
from backend.execution.provider_session import ProviderSession
from backend.execution.repository import SegmentRepository

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """
    Generic execution engine. Created once at application start.
    Lives for the lifetime of the application. Multiple jobs share it.

    Emits events via the on_event callback for profiling/monitoring:
      request_queued, request_started, request_completed, request_failed,
      request_retry, request_timeout, request_cancelled
    """

    def __init__(
        self,
        session: ProviderSession,
        max_concurrent: int = 3,
        on_event: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
    ):
        self.session = session
        self._max_concurrent = max_concurrent
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._workers: list[asyncio.Task] = []
        self._running = False
        self._metrics = ExecutionMetrics()
        self._active_handles: dict[str, ExecutionHandle] = {}
        self._on_event = on_event

    async def start(self, num_workers: int = 3):
        """Start worker loops."""
        self._running = True
        self._workers = [
            asyncio.create_task(self._worker_loop(i))
            for i in range(num_workers)
        ]
        logger.info("ExecutionEngine started with %d workers", num_workers)

    async def stop(self):
        """Stop all workers and drain the queue."""
        self._running = False
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("ExecutionEngine stopped")

    def submit(self, request: ExecutionRequest, repo: SegmentRepository) -> ExecutionHandle:
        """
        Submit request. Resolves prompt via builder + repo at execution time.
        Returns a handle for tracking/cancellation.
        """
        handle = ExecutionHandle(request)
        self._active_handles[request.request_id] = handle
        self._queue.put_nowait((request.priority.value, time.monotonic(), request, repo))
        self._metrics.queue_length = self._queue.qsize()

        # Emit event synchronously (fire-and-forget via create_task if needed)
        if self._on_event:
            asyncio.create_task(self._emit("request_queued", {
                "request_id": request.request_id,
                "stage": request.stage.name,
                "priority": request.priority.name,
                "queue_size": self._queue.qsize(),
            }))

        return handle

    def cancel(self, request_id: str) -> bool:
        """Cancel a request by ID. Marks handle cancelled; queue cleanup is periodic."""
        handle = self._active_handles.get(request_id)
        if handle and not handle.is_done:
            handle.cancel()
            if self._on_event:
                asyncio.create_task(self._emit("request_cancelled", {
                    "request_id": request_id,
                }))
            return True
        return False

    def get_metrics(self) -> ExecutionMetrics:
        self._metrics.queue_length = self._queue.qsize()
        return self._metrics

    def cleanup_cancelled(self):
        """Compact the queue by removing cancelled requests. Called periodically by workers."""
        items = []
        while not self._queue.empty():
            try:
                items.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        for priority, ts, request, repo in items:
            handle = self._active_handles.get(request.request_id)
            if not (handle and handle.is_cancelled):
                self._queue.put_nowait((priority, ts, request, repo))
        self._metrics.queue_length = self._queue.qsize()

    async def _emit(self, event_name: str, payload: dict[str, Any]):
        """Emit an event via the callback. Catches exceptions to avoid breaking the engine."""
        if self._on_event:
            try:
                await self._on_event(event_name, payload)
            except Exception as e:
                logger.warning("Event emission failed for %s: %s", event_name, e)

    async def _worker_loop(self, worker_id: int):
        """Main worker loop. Dequeues and executes requests."""
        cleanup_counter = 0
        while self._running:
            try:
                priority, ts, request, repo = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                # Periodic cleanup of cancelled requests
                cleanup_counter += 1
                if cleanup_counter >= 10:
                    cleanup_counter = 0
                    self.cleanup_cancelled()
                continue

            handle = self._active_handles.get(request.request_id)
            if handle and handle.is_cancelled:
                continue

            self._metrics.running += 1
            self._metrics.workers_busy += 1
            try:
                result = await self._execute_with_retry(request, handle, repo)
            finally:
                self._metrics.running -= 1
                self._metrics.workers_busy -= 1

            if handle:
                if result.status == "completed":
                    self._metrics.completed += 1
                    self._metrics.total_tokens += result.metrics.tokens_used
                    handle._metrics = result.metrics
                    handle._future.set_result(result)
                    await self._emit("request_completed", {
                        "request_id": request.request_id,
                        "tokens": result.metrics.tokens_used,
                        "execution_time": result.metrics.execution_time,
                    })
                elif result.status == "timeout":
                    self._metrics.timeouts += 1
                    handle._future.set_exception(TimeoutError(
                        f"Request {request.request_id} timed out after "
                        f"{request.timeout_policy.max_total_seconds}s"
                    ))
                    await self._emit("request_timeout", {
                        "request_id": request.request_id,
                    })
                else:
                    self._metrics.failures += 1
                    handle._future.set_exception(result.error or Exception("Unknown error"))
                    await self._emit("request_failed", {
                        "request_id": request.request_id,
                        "error": str(result.error),
                        "retryable": result.retryable,
                    })

    async def _execute_with_retry(
        self,
        request: ExecutionRequest,
        handle: ExecutionHandle | None,
        repo: SegmentRepository,
    ) -> ExecutionResult:
        """Execute a request with retry logic. Respects retryable vs non-retryable errors."""
        retry_policy = request.retry_policy
        timeout_policy = request.timeout_policy
        start = time.monotonic()
        last_result = None

        for attempt in range(1, retry_policy.max_attempts + 1):
            # Check cancellation
            if handle and handle.is_cancelled:
                return ExecutionResult(
                    request_id=request.request_id,
                    raw_response={},
                    status="failed",
                    error=asyncio.CancelledError(),
                    retryable=False,
                )

            # Check total timeout
            elapsed = time.monotonic() - start
            if elapsed > timeout_policy.max_total_seconds:
                return ExecutionResult(
                    request_id=request.request_id,
                    raw_response={},
                    status="timeout",
                    error=TimeoutError(),
                    retryable=False,
                )

            # Resolve prompt at execution time: builder + context + repo -> prompt
            prompt = request.prompt_builder.build(request.prompt_context, repo)

            await self._emit("request_started", {
                "request_id": request.request_id,
                "attempt": attempt,
            })

            try:
                result = await asyncio.wait_for(
                    self.session.execute(prompt, request.request_id),
                    timeout=timeout_policy.max_execution_seconds,
                )
            except asyncio.TimeoutError:
                result = ExecutionResult(
                    request_id=request.request_id,
                    raw_response={},
                    status="timeout",
                    error=TimeoutError(f"Single attempt timed out after {timeout_policy.max_execution_seconds}s"),
                    retryable=True,
                )

            if result.status == "completed":
                result.metrics.attempt = attempt
                result.metrics.queue_time = result.metrics.started_at - start if result.metrics.started_at else 0
                result.metrics.total_time = time.monotonic() - start
                return result

            last_result = result

            # Don't retry non-retryable errors
            if not result.retryable:
                logger.info("Request %s failed with non-retryable error: %s",
                           request.request_id, result.error)
                return result

            self._metrics.retries += 1
            await self._emit("request_retry", {
                "request_id": request.request_id,
                "attempt": attempt,
                "error": str(result.error),
            })

            if attempt < retry_policy.max_attempts:
                delay = min(
                    retry_policy.base_delay * (retry_policy.exponential_base ** (attempt - 1)),
                    retry_policy.max_delay,
                )
                await asyncio.sleep(delay)

        return last_result


class PipelineExecutor:
    """
    Orchestrates pipeline stages. Registers stages dynamically.
    Submits requests, waits for stages, returns handles/results.
    Does NOT parse results — pipeline decides what to do with them.
    """

    def __init__(self, engine: ExecutionEngine):
        self.engine = engine
        self._stages: list[PipelineStage] = []
        self._stage_handles: dict[PipelineStage, list[ExecutionHandle]] = {}

    def register_stage(self, stage: PipelineStage):
        if stage not in self._stages:
            self._stages.append(stage)
            self._stages.sort(key=lambda s: s.priority)

    def submit_stage(
        self,
        stage: PipelineStage,
        requests: list[ExecutionRequest],
        repo: SegmentRepository,
    ) -> list[ExecutionHandle]:
        """Submit all requests for a stage. Returns handles."""
        handles = [self.engine.submit(req, repo) for req in requests]
        self._stage_handles[stage] = handles
        return handles

    async def wait_for_stage(self, stage: PipelineStage) -> list[ExecutionHandle]:
        """Wait for all handles in a stage. Returns handles — caller reads results."""
        handles = self._stage_handles.get(stage, [])
        for handle in handles:
            try:
                await handle.result()
            except Exception:
                pass  # Individual errors are on the handle; caller inspects
        return handles

    def get_handles(self, stage: PipelineStage) -> list[ExecutionHandle]:
        return self._stage_handles.get(stage, [])

    def get_all_handles(self) -> list[ExecutionHandle]:
        all_handles = []
        for handles in self._stage_handles.values():
            all_handles.extend(handles)
        return all_handles

    def cancel_stage(self, stage: PipelineStage) -> int:
        """Cancel all handles in a stage. Returns count cancelled."""
        handles = self._stage_handles.get(stage, [])
        count = 0
        for handle in handles:
            if handle.cancel():
                count += 1
        return count
