from __future__ import annotations

import asyncio
import logging
import time

from backend.execution.execution_policy import ExecutionPolicy
from backend.execution.model_registry import ModelRegistry
from backend.execution.models import (
    LLMExecutionResult,
    LLMTask,
    RequestMetrics,
    TaskState,
)
from backend.execution.token_budget import TokenBudget
from backend.services.prompt_store import PromptStore

logger = logging.getLogger(__name__)


class ProviderAdapter:
    """Model-aware provider execution.

    Wraps the existing provider with token budget, circuit breaker, and retry logic.
    Resolves prompts from PromptStore at execution time.
    """

    def __init__(
        self,
        model_registry: ModelRegistry,
        execution_policy: ExecutionPolicy,
        token_budget: TokenBudget,
        prompt_store: PromptStore,
    ):
        self.registry = model_registry
        self.policy = execution_policy
        self.budget = token_budget
        self.prompt_store = prompt_store

    async def execute(self, task: LLMTask) -> LLMExecutionResult:
        """Execute task with model-aware provider selection and retry."""
        model_config = self.registry.get_config(task.model_name)
        provider = self.registry.get_provider(task.model_name)

        if not self.policy.can_execute():
            return LLMExecutionResult(
                task_id=task.task_id,
                status="failed",
                error="Circuit breaker is open",
                task_state=TaskState.FAILED,
            )

        reservation = await self.budget.reserve(task.estimated_total_tokens, timeout=30.0)
        if not reservation:
            return LLMExecutionResult(
                task_id=task.task_id,
                status="failed",
                error="Insufficient token budget after waiting",
                task_state=TaskState.FAILED,
            )

        task.transition(TaskState.EXECUTING)
        prompt_content = self.prompt_store.get(task.prompt_id)

        last_error = None
        actual_tokens_used = 0

        for attempt in range(self.policy.max_retries):
            try:
                start = time.monotonic()
                result = await asyncio.wait_for(
                    asyncio.to_thread(provider.complete, prompt_content),
                    timeout=self.policy.request_timeout,
                )
                elapsed = time.monotonic() - start

                actual_tokens = result.get("_usage", {}).get("total_tokens", task.estimated_total_tokens)
                actual_tokens_used = actual_tokens

                await self.budget.commit(reservation.reservation_id, actual_tokens)
                self.prompt_store.release(task.prompt_id)
                self.policy.record_success()

                return LLMExecutionResult(
                    task_id=task.task_id,
                    status="completed",
                    data=result,
                    task_state=TaskState.COMPLETED,
                    reservation_id=reservation.reservation_id,
                    actual_tokens=actual_tokens,
                    metrics=RequestMetrics(
                        started_at=start,
                        completed_at=start + elapsed,
                        execution_time=elapsed,
                        tokens_used=actual_tokens,
                        attempt=attempt + 1,
                    ),
                )

            except Exception as e:
                last_error = e
                task.transition(TaskState.RETRYING)
                is_rate_limit = "rate" in str(e).lower() or "429" in str(e)
                self.policy.record_failure(is_rate_limit=is_rate_limit)

                if actual_tokens_used > 0:
                    await self.budget.commit(reservation.reservation_id, actual_tokens_used)
                else:
                    await self.budget.rollback(reservation.reservation_id)

                if attempt < self.policy.max_retries - 1:
                    delay = self.policy.calculate_backoff(attempt, e)
                    logger.warning(
                        "ProviderAdapter: task %s attempt %d failed (%s), retry in %.1fs",
                        task.task_id, attempt + 1, type(e).__name__, delay,
                    )
                    await asyncio.sleep(delay)

        self.prompt_store.release(task.prompt_id)

        return LLMExecutionResult(
            task_id=task.task_id,
            status="failed",
            error=str(last_error),
            task_state=TaskState.FAILED,
            reservation_id=reservation.reservation_id,
            actual_tokens=actual_tokens_used,
        )
