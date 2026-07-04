from __future__ import annotations

import logging
import time
from typing import Any

from backend.execution.engine import ExecutionEngine
from backend.execution.models import ExecutionMetrics

logger = logging.getLogger(__name__)


class ExecutionProfiler:
    """
    Event-based profiler that tracks execution engine metrics.
    Uses the engine's on_event callback to collect timing data.
    """

    def __init__(self, engine: ExecutionEngine):
        self._engine = engine
        self._timings: dict[str, dict[str, float]] = {}
        self._request_events: list[dict[str, Any]] = []

    async def handle_event(self, event_name: str, payload: dict[str, Any]) -> None:
        """Handle an engine event for profiling."""
        req_id = payload.get("request_id", "")
        now = time.monotonic()

        if req_id not in self._timings:
            self._timings[req_id] = {}

        self._timings[req_id][event_name] = now

        self._request_events.append({
            "event": event_name,
            "request_id": req_id,
            "timestamp": now,
            **payload,
        })

    def report(self) -> dict[str, Any]:
        """Generate a profiling report from collected metrics."""
        total_queue_time = 0.0
        total_execution_time = 0.0
        count = 0

        for timings in self._timings.values():
            queued = timings.get("request_queued", 0)
            started = timings.get("request_started", 0)
            completed = timings.get("request_completed", 0)

            if queued and started:
                total_queue_time += started - queued
                count += 1
            if started and completed:
                total_execution_time += completed - started

        engine_metrics = self._engine.get_metrics()

        return {
            "total_requests": len(self._timings),
            "avg_queue_time": total_queue_time / count if count else 0,
            "avg_execution_time": total_execution_time / count if count else 0,
            "engine_metrics": {
                "completed": engine_metrics.completed,
                "failures": engine_metrics.failures,
                "retries": engine_metrics.retries,
                "timeouts": engine_metrics.timeouts,
                "total_tokens": engine_metrics.total_tokens,
            },
            "events": self._request_events[-100:],  # Last 100 events
        }
