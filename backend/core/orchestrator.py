# backend/core/orchestrator.py

from dataclasses import dataclass, field
from typing import Optional
import time
from backend.core.dag import DAGExecutor, DAGNode, ExecutionResult
from backend.core.context import ExecutionContext
from backend.core.artifact import Artifact


@dataclass
class StageDefinition:
    """Defines a pipeline stage for the orchestrator."""
    name: str
    stage_fn: object  # callable
    depends_on: list = field(default_factory=list)
    budget_ms: float = 1000.0
    priority: int = 0
    thread_safe: str = "safe"


class PipelineOrchestrator:
    """Lightweight orchestrator that wires stages into a DAG and executes."""

    def __init__(self, max_concurrency: int = 10):
        self._stages: list[StageDefinition] = []
        self._max_concurrency = max_concurrency

    def add_stage(self, stage: StageDefinition):
        self._stages.append(stage)

    def build_dag(self) -> DAGExecutor:
        dag = DAGExecutor(max_concurrency=self._max_concurrency)
        for stage in self._stages:
            dag.add_node(DAGNode(
                name=stage.name,
                stage_fn=stage.stage_fn,
                depends_on=stage.depends_on,
                budget_ms=stage.budget_ms,
                priority=stage.priority,
                thread_safe=stage.thread_safe,
            ))
        return dag

    async def execute(
        self,
        context: ExecutionContext,
        initial_artifacts: dict[str, Artifact] = None,
    ) -> ExecutionResult:
        dag = self.build_dag()
        start = time.monotonic()
        result = await dag.execute(initial_artifacts or {})
        elapsed = (time.monotonic() - start) * 1000

        # Record metrics
        context.record_metric("pipeline_total_ms", elapsed)
        context.record_metric("pipeline_nodes_executed", result.nodes_executed)
        context.record_metric("pipeline_nodes_failed", result.nodes_failed)

        return result
