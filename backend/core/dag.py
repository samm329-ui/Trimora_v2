# backend/core/dag.py

from dataclasses import dataclass, field
from typing import Callable, Optional
import asyncio
import time
import traceback
from backend.core.artifact import Artifact, ErrorArtifact, ErrorSeverity, ArtifactStatus


class DependencyPolicy:
    """How a node depends on its predecessors."""
    SUCCESS = "success"
    ANY = "any"
    OPTIONAL = "optional"


@dataclass
class DAGNode:
    """A node in the execution DAG."""
    name: str
    stage_fn: Callable
    depends_on: list = field(default_factory=list)
    dependency_policy: str = DependencyPolicy.SUCCESS
    budget_ms: float = 1000.0
    thread_safe: str = "safe"
    priority: int = 0  # Lower = higher priority


@dataclass(frozen=True)
class ExecutionResult:
    """Unified result of a pipeline execution — immutable."""
    artifacts: dict
    errors: dict
    trace: list
    latency_stats: dict
    warnings: list
    total_ms: float
    nodes_executed: int
    nodes_succeeded: int
    nodes_failed: int
    nodes_skipped: int


class BudgetEnforcer:
    """Automatic enforcement: warning -> count -> disable -> fallback."""

    def __init__(self, warning_threshold: float = 0.8, max_warnings: int = 3):
        self.warning_threshold = warning_threshold
        self.max_warnings = max_warnings
        self._warning_counts: dict = {}
        self._disabled: set = set()

    def check(self, stage_name: str, elapsed_ms: float, budget_ms: float) -> Optional[str]:
        """Returns action: None=ok, 'warning', 'disabled'."""
        if stage_name in self._disabled:
            return "disabled"

        if elapsed_ms > budget_ms:
            count = self._warning_counts.get(stage_name, 0) + 1
            self._warning_counts[stage_name] = count
            if count >= self.max_warnings:
                self._disabled.add(stage_name)
                return "disabled"
            return "warning"

        if elapsed_ms > budget_ms * self.warning_threshold:
            count = self._warning_counts.get(stage_name, 0) + 1
            self._warning_counts[stage_name] = count
            if count >= self.max_warnings:
                self._disabled.add(stage_name)
                return "disabled"
            return "warning"

        return None

    def is_disabled(self, stage_name: str) -> bool:
        return stage_name in self._disabled

    def reset(self, stage_name: str = None):
        if stage_name:
            self._warning_counts.pop(stage_name, None)
            self._disabled.discard(stage_name)
        else:
            self._warning_counts.clear()
            self._disabled.clear()


class DAGExecutor:
    """Execute a DAG of stages with concurrency limits, priority scheduling, and ExecutionResult."""

    def __init__(self, max_concurrency: int = 10):
        self._nodes: dict = {}
        self._artifacts: dict = {}
        self._errors: dict = {}
        self._trace: list = []
        self._latency_stats: dict = {}
        self._warnings: list = []
        self._max_concurrency = max_concurrency
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._budget_enforcer = BudgetEnforcer()

    def add_node(self, node: DAGNode):
        self._nodes[node.name] = node

    async def execute(self, initial_artifacts: dict = None) -> ExecutionResult:
        self._semaphore = asyncio.Semaphore(self._max_concurrency)
        start_time = time.monotonic()

        in_degree = {name: 0 for name in self._nodes}
        for name, node in self._nodes.items():
            for dep in node.depends_on:
                if dep in self._nodes:
                    in_degree[name] += 1

        if initial_artifacts:
            self._artifacts.update(initial_artifacts)

        ready = [name for name, degree in in_degree.items() if degree == 0]
        executed = set()
        succeeded = set()
        skipped = set()

        while ready:
            # Priority sort: lower priority number = executed first
            ready.sort(key=lambda n: self._nodes[n].priority)

            tasks = []
            task_names = []
            for name in ready:
                if name in executed:
                    continue

                node = self._nodes[name]

                # Check if disabled by budget enforcer
                if self._budget_enforcer.is_disabled(name):
                    self._warnings.append(f"{name} disabled by budget enforcement")
                    skipped.add(name)
                    executed.add(name)
                    continue

                # Check dependency policy
                can_execute = True
                for dep in node.depends_on:
                    if dep not in executed:
                        can_execute = False
                        break
                    if node.dependency_policy == DependencyPolicy.SUCCESS and dep in self._errors:
                        can_execute = False
                        skipped.add(name)
                        executed.add(name)
                        break

                if can_execute:
                    inputs = {}
                    for dep in node.depends_on:
                        if dep in self._artifacts:
                            inputs[dep] = self._artifacts[dep]
                        elif dep in self._errors:
                            inputs[dep] = self._errors[dep]
                    tasks.append(self._execute_node(name, node, inputs))
                    task_names.append(name)
                else:
                    skipped.add(name)

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for name, result in zip(task_names, results):
                    executed.add(name)
                    if isinstance(result, ErrorArtifact):
                        self._errors[name] = result
                    elif isinstance(result, Artifact):
                        self._artifacts[name] = result
                        succeeded.add(name)
                    elif isinstance(result, Exception):
                        self._errors[name] = ErrorArtifact(
                            reason=str(result),
                            stage=name,
                            stacktrace=traceback.format_exc(),
                            severity=ErrorSeverity.ERROR,
                            recoverable=False,
                            error_code=type(result).__name__,
                        )

            # Recalculate ready nodes
            ready = []
            for name in self._nodes:
                if name not in executed:
                    node = self._nodes[name]
                    all_deps_met = all(dep in executed for dep in node.depends_on)
                    if all_deps_met:
                        ready.append(name)

        total_ms = (time.monotonic() - start_time) * 1000

        return ExecutionResult(
            artifacts=dict(self._artifacts),
            errors=dict(self._errors),
            trace=list(self._trace),
            latency_stats=self._compute_stats(),
            warnings=list(self._warnings),
            total_ms=total_ms,
            nodes_executed=len(executed),
            nodes_succeeded=len(succeeded),
            nodes_failed=len(self._errors),
            nodes_skipped=len(skipped),
        )

    async def _execute_node(self, name: str, node: DAGNode, inputs: dict):
        async with self._semaphore:
            start = time.monotonic()
            try:
                # Check if stage_fn is async
                if asyncio.iscoroutinefunction(node.stage_fn):
                    result = await node.stage_fn(inputs)
                else:
                    result = node.stage_fn(inputs)

                elapsed_ms = (time.monotonic() - start) * 1000

                # Budget enforcement
                budget_action = self._budget_enforcer.check(name, elapsed_ms, node.budget_ms)
                if budget_action == "disabled":
                    self._warnings.append(
                        f"{name} disabled after exceeding budget {node.budget_ms}ms"
                    )
                elif budget_action == "warning":
                    self._warnings.append(
                        f"{name} exceeded budget: {elapsed_ms:.0f}ms > {node.budget_ms}ms"
                    )

                # Record latency
                if name not in self._latency_stats:
                    self._latency_stats[name] = []
                self._latency_stats[name].append(elapsed_ms)

                self._trace.append({
                    "stage": name,
                    "input_types": list(inputs.keys()),
                    "output_type": type(result).__name__,
                    "elapsed_ms": elapsed_ms,
                    "budget_ms": node.budget_ms,
                    "artifact_id": result.artifact_id if hasattr(result, 'artifact_id') else "",
                    "status": "success",
                    "timestamp": time.time(),
                })

                return result

            except Exception as e:
                elapsed_ms = (time.monotonic() - start) * 1000
                self._trace.append({
                    "stage": name,
                    "input_types": list(inputs.keys()),
                    "output_type": "ErrorArtifact",
                    "elapsed_ms": elapsed_ms,
                    "budget_ms": node.budget_ms,
                    "artifact_id": "",
                    "status": "error",
                    "error": str(e),
                    "timestamp": time.time(),
                })
                return ErrorArtifact(
                    reason=str(e),
                    stage=name,
                    stacktrace=traceback.format_exc(),
                    severity=ErrorSeverity.ERROR,
                    recoverable=False,
                    error_code=type(e).__name__,
                )

    def _compute_stats(self) -> dict:
        stats = {}
        for name, latencies in self._latency_stats.items():
            sorted_lat = sorted(latencies)
            n = len(sorted_lat)
            if n == 0:
                continue
            p50_idx = n // 2
            if n % 2 == 0 and n > 0:
                p50 = (sorted_lat[p50_idx - 1] + sorted_lat[p50_idx]) / 2
            else:
                p50 = sorted_lat[p50_idx]
            p95_idx = max(0, int(n * 0.95) - 1)
            stats[name] = {
                "p50": p50,
                "p95": sorted_lat[p95_idx],
                "max": max(sorted_lat),
                "count": n,
            }
        return stats
