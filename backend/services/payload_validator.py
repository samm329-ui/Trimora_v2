from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.config.models import ModelConfig
from backend.execution.models import LLMTask
from backend.services.token_counter import TokenCounter

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of payload validation."""

    valid: bool
    reason: str
    error_code: str


@dataclass
class SplitRecommendation:
    """Recommendation for how to split an oversized payload."""

    needs_split: bool
    recommended_chunks: int
    chunk_size: int
    strategy: str  # "transcript", "json", "reasoning", "summary"


class PayloadValidator:
    """Validates task payloads against model limits.

    Validation only — no splitting logic here.
    """

    def __init__(self, token_counter: TokenCounter):
        self.counter = token_counter

    def validate(self, task: LLMTask, model_config: ModelConfig) -> ValidationResult:
        """Validate task payload against model limits."""
        total_tokens = task.estimated_total_tokens

        if total_tokens > model_config.max_input_tokens:
            return ValidationResult(
                valid=False,
                reason=f"Prompt too large: {task.prompt_tokens} tokens exceeds max_input_tokens {model_config.max_input_tokens}",
                error_code="PAYLOAD_TOO_LARGE",
            )

        if task.expected_output_tokens > model_config.max_output_tokens:
            return ValidationResult(
                valid=False,
                reason=f"Expected output {task.expected_output_tokens} exceeds max_output_tokens {model_config.max_output_tokens}",
                error_code="OUTPUT_TOO_LARGE",
            )

        if total_tokens > model_config.max_payload_tokens:
            return ValidationResult(
                valid=False,
                reason=f"Total payload {total_tokens} exceeds max_payload_tokens {model_config.max_payload_tokens}",
                error_code="PAYLOAD_EXCEEDS_LIMIT",
            )

        return ValidationResult(valid=True, reason="", error_code="")

    def get_split_recommendation(
        self,
        task: LLMTask,
        model_config: ModelConfig,
    ) -> SplitRecommendation:
        """Recommend how to split if needed."""
        if task.prompt_tokens <= model_config.max_input_tokens:
            return SplitRecommendation(
                needs_split=False,
                recommended_chunks=1,
                chunk_size=task.prompt_tokens,
                strategy=task.task_type,
            )

        chunk_size = int(model_config.max_input_tokens * 0.9)
        recommended_chunks = max(2, -(-task.prompt_tokens // chunk_size))

        strategy_map = {
            "annotation": "transcript",
            "reasoning": "reasoning",
            "summary": "summary",
        }
        strategy = strategy_map.get(task.task_type, "transcript")

        return SplitRecommendation(
            needs_split=True,
            recommended_chunks=recommended_chunks,
            chunk_size=chunk_size,
            strategy=strategy,
        )
