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


# ===========================================================================
# LLM Scheduler Types
# ===========================================================================


# ---------------------------------------------------------------------------
# TaskState — lifecycle states for LLM tasks
# ---------------------------------------------------------------------------

class TaskState(Enum):
    CREATED = "created"
    QUEUED = "queued"
    WAITING_FOR_BUDGET = "waiting_for_budget"
    EXECUTING = "executing"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# TaskPriority — alias for RequestPriority
# ---------------------------------------------------------------------------

TaskPriority = RequestPriority


# ---------------------------------------------------------------------------
# SplitMetadata — metadata for split chunks (reassembly)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SplitMetadata:
    """Metadata for split chunks. Enables deterministic reassembly."""

    original_prompt_id: str
    chunk_index: int
    total_chunks: int
    start_offset: int
    end_offset: int
    original_token_count: int


# ---------------------------------------------------------------------------
# LLMTask — a single LLM execution unit
# ---------------------------------------------------------------------------

@dataclass
class LLMTask:
    """A single LLM execution unit with token accounting."""

    task_id: str
    prompt_id: str
    prompt_tokens: int
    expected_output_tokens: int
    model_name: str
    job_id: str
    stage: str
    task_type: str = "general"
    priority: TaskPriority = TaskPriority.NORMAL
    state: TaskState = TaskState.CREATED
    state_history: list[tuple[TaskState, float]] = field(default_factory=list)
    split_metadata: SplitMetadata | None = None
    created_at: float = field(default_factory=time.monotonic)

    def transition(self, new_state: TaskState) -> None:
        """Transition to a new state, recording history."""
        self.state = new_state
        self.state_history.append((new_state, time.monotonic()))

    @property
    def estimated_total_tokens(self) -> int:
        return self.prompt_tokens + self.expected_output_tokens


# ---------------------------------------------------------------------------
# generate_task_id — deterministic task ID from job + stage + prompt_hash
# ---------------------------------------------------------------------------

def generate_task_id(job_id: str, stage: str, prompt_hash: str, chunk: int = 0) -> str:
    """Generate a deterministic task ID."""
    return f"{job_id}_{stage}_{prompt_hash[:8]}_{chunk}"


# ---------------------------------------------------------------------------
# LLMExecutionResult — result from LLM scheduler execution
# ---------------------------------------------------------------------------

@dataclass
class LLMExecutionResult:
    """Result from LLM scheduler execution."""

    task_id: str
    status: str  # "completed" | "failed"
    data: dict = field(default_factory=dict)
    error: str | None = None
    task_state: TaskState = TaskState.COMPLETED
    reservation_id: str | None = None
    actual_tokens: int = 0
    metrics: RequestMetrics = field(default_factory=RequestMetrics)


# ---------------------------------------------------------------------------
# LLMExecutionHandle — tracks async LLM task completion
# ---------------------------------------------------------------------------

class LLMExecutionHandle:
    """Handle for tracking async LLM task completion."""

    def __init__(self, task: LLMTask):
        self._task = task
        self._future: asyncio.Future[LLMExecutionResult] = asyncio.get_running_loop().create_future()

    @property
    def task(self) -> LLMTask:
        return self._task

    @property
    def task_id(self) -> str:
        return self._task.task_id

    async def result(self) -> LLMExecutionResult:
        return await self._future

    def set_result(self, result: LLMExecutionResult) -> None:
        if not self._future.done():
            self._future.set_result(result)

    def set_error(self, error: Exception) -> None:
        if not self._future.done():
            self._future.set_exception(error)

    def done(self) -> bool:
        return self._future.done()

    @property
    def is_done(self) -> bool:
        return self._future.done()


# ---------------------------------------------------------------------------
# SchedulerMetrics — scheduler-level metrics
# ---------------------------------------------------------------------------

@dataclass
class SchedulerMetrics:
    """Scheduler-level metrics."""

    submitted: int = 0
    completed: int = 0
    failed: int = 0
    retried: int = 0
    total_tokens: int = 0
    queue_wait_total: float = 0.0
    execution_time_total: float = 0.0
    active_workers: int = 0
    worker_exceptions: int = 0
    queue_depth_peak: int = 0

    def record_submission(self, task: LLMTask) -> None:
        self.submitted += 1

    def record_completion(self, task: LLMTask, result: LLMExecutionResult) -> None:
        self.completed += 1
        self.total_tokens += result.actual_tokens or 0

    def record_error(self, task: LLMTask, error: Exception) -> None:
        self.failed += 1

    def record_queue_depth(self, depth: int) -> None:
        if depth > self.queue_depth_peak:
            self.queue_depth_peak = depth

    def to_dict(self) -> dict:
        return {
            "submitted": self.submitted,
            "completed": self.completed,
            "failed": self.failed,
            "retried": self.retried,
            "total_tokens": self.total_tokens,
            "active_workers": self.active_workers,
            "worker_exceptions": self.worker_exceptions,
            "queue_depth_peak": self.queue_depth_peak,
        }
