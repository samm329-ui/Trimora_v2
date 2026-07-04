from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.execution.repository import SegmentRepository


# ---------------------------------------------------------------------------
# PromptBuilder + PromptContext — lightweight identifiers, not full objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PromptContext:
    """
    Lightweight, immutable context for prompt construction.
    Contains identifiers and precomputed slices — NOT full objects.
    PromptBuilder resolves IDs through a read-only repository.
    """
    block_index: int = 0
    batch_index: int = 0
    segment_ids: tuple[int, ...] = ()
    context_before_ids: tuple[int, ...] = ()
    context_after_ids: tuple[int, ...] = ()
    summary: str = ""
    adjacent_block_indices: tuple[int, ...] = ()
    extra: dict = field(default_factory=dict)


class PromptBuilder(ABC):
    """Each service implements this. Pure function: context + repository -> prompt string."""

    @abstractmethod
    def build(self, context: PromptContext, repo: SegmentRepository) -> str:
        pass


# ---------------------------------------------------------------------------
# RequestPriority — enum
# ---------------------------------------------------------------------------

class RequestPriority(Enum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


# ---------------------------------------------------------------------------
# PipelineStage — dynamic registration
# ---------------------------------------------------------------------------

@dataclass
class PipelineStage:
    name: str
    priority: int = 0

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return isinstance(other, PipelineStage) and self.name == other.name


STAGE_SUMMARY = PipelineStage("summary", priority=0)
STAGE_PASS1 = PipelineStage("pass1", priority=1)
STAGE_PASS2 = PipelineStage("pass2", priority=2)
STAGE_BLUEPRINT = PipelineStage("blueprint", priority=3)


# ---------------------------------------------------------------------------
# RetryPolicy — retry configuration
# ---------------------------------------------------------------------------

@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0


# ---------------------------------------------------------------------------
# TimeoutPolicy — abort requests that take too long
# ---------------------------------------------------------------------------

@dataclass
class TimeoutPolicy:
    max_execution_seconds: float = 60.0
    max_total_seconds: float = 300.0


# ---------------------------------------------------------------------------
# ProgressInfo — per-handle progress
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProgressInfo:
    completed: int = 0
    total: int = 1
    stage: PipelineStage | None = None

    @property
    def percent(self) -> float:
        return (self.completed / max(self.total, 1)) * 100


# ---------------------------------------------------------------------------
# RequestMetrics — per-request timing
# ---------------------------------------------------------------------------

@dataclass
class RequestMetrics:
    created_at: float = 0.0
    queued_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    attempt: int = 0
    queue_time: float = 0.0
    execution_time: float = 0.0
    total_time: float = 0.0
    tokens_used: int = 0


# ---------------------------------------------------------------------------
# ExecutionMetrics — engine-level
# ---------------------------------------------------------------------------

@dataclass
class ExecutionMetrics:
    queue_length: int = 0
    workers_busy: int = 0
    running: int = 0
    completed: int = 0
    retries: int = 0
    failures: int = 0
    timeouts: int = 0
    throughput: float = 0.0
    average_wait: float = 0.0
    average_execution: float = 0.0
    total_tokens: int = 0


# ---------------------------------------------------------------------------
# ExecutionRequest — immutable input
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExecutionRequest:
    request_id: str
    prompt_builder: PromptBuilder
    prompt_context: PromptContext
    stage: PipelineStage
    priority: RequestPriority = RequestPriority.NORMAL
    metadata: dict = field(default_factory=dict)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    timeout_policy: TimeoutPolicy = field(default_factory=TimeoutPolicy)


# ---------------------------------------------------------------------------
# ExecutionResult — raw response
# ---------------------------------------------------------------------------

@dataclass
class ExecutionResult:
    request_id: str
    raw_response: dict
    status: str  # "completed" | "failed" | "timeout"
    metrics: RequestMetrics = field(default_factory=RequestMetrics)
    error: Exception | None = None
    retryable: bool = True


# ---------------------------------------------------------------------------
# HandleSnapshot — immutable state view
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HandleSnapshot:
    request_id: str
    status: str  # "pending" | "running" | "completed" | "failed" | "cancelled"
    progress: ProgressInfo
    metrics: RequestMetrics


# ---------------------------------------------------------------------------
# ExecutionHandle — owns execution state
# ---------------------------------------------------------------------------

class ExecutionHandle:
    def __init__(self, request: ExecutionRequest):
        self._request = request
        self._future: asyncio.Future[ExecutionResult] = asyncio.get_event_loop().create_future()
        self._cancelled = False
        self._progress = ProgressInfo()
        self._metrics = RequestMetrics(created_at=time.monotonic())

    @property
    def request(self) -> ExecutionRequest:
        return self._request

    @property
    def request_id(self) -> str:
        return self._request.request_id

    async def result(self) -> ExecutionResult:
        return await self._future

    def cancel(self) -> bool:
        if self._future.done():
            return False
        self._cancelled = True
        self._future.cancel()
        return True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    @property
    def is_done(self) -> bool:
        return self._future.done()

    def snapshot(self) -> HandleSnapshot:
        if self._cancelled:
            status = "cancelled"
        elif self._future.done():
            try:
                result = self._future.result()
                status = result.status
            except Exception:
                status = "failed"
        else:
            status = "pending"
        return HandleSnapshot(
            request_id=self._request.request_id,
            status=status,
            progress=self._progress,
            metrics=self._metrics,
        )
