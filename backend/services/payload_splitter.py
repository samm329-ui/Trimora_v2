from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod

from backend.execution.models import LLMTask, SplitMetadata, TaskPriority, generate_task_id
from backend.services.prompt_store import PromptStore
from backend.services.token_counter import TokenCounter

logger = logging.getLogger(__name__)


class SplitStrategy(ABC):
    """Base class for prompt splitting strategies."""

    @abstractmethod
    def split(self, content: str, max_tokens: int, counter: TokenCounter) -> list[str]:
        ...


class TranscriptSplitter(SplitStrategy):
    """Split by paragraphs/speaker turns, respecting transcript structure."""

    def split(self, content: str, max_tokens: int, counter: TokenCounter) -> list[str]:
        paragraphs = content.split("\n\n")
        chunks = []
        current_chunk = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = counter.count(para)
            if current_tokens + para_tokens > max_tokens and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [para]
                current_tokens = para_tokens
            else:
                current_chunk.append(para)
                current_tokens += para_tokens

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks if chunks else [content]


class ReasoningSplitter(SplitStrategy):
    """Split reasoning prompts while preserving SYSTEM/USER structure."""

    def split(self, content: str, max_tokens: int, counter: TokenCounter) -> list[str]:
        lines = content.split("\n")
        header_lines = []
        body_lines = []
        in_body = False

        for line in lines:
            if not in_body and any(kw in line.upper() for kw in ["SYSTEM:", "INSTRUCTIONS:", "JSON SCHEMA:"]):
                in_body = True
            if in_body:
                body_lines.append(line)
            else:
                header_lines.append(line)

        if not body_lines:
            return TranscriptSplitter().split(content, max_tokens, counter)

        header = "\n".join(header_lines)
        header_tokens = counter.count(header)

        effective_max = max_tokens - header_tokens
        if effective_max <= 0:
            return [content]

        body_chunks = TranscriptSplitter().split("\n".join(body_lines), effective_max, counter)
        return [f"{header}\n{chunk}" for chunk in body_chunks]


class SummarySplitter(SplitStrategy):
    """Split summary prompts by topic blocks."""

    def split(self, content: str, max_tokens: int, counter: TokenCounter) -> list[str]:
        return TranscriptSplitter().split(content, max_tokens, counter)


class PayloadSplitter:
    """Split oversized prompts using task-specific strategies."""

    def __init__(self, token_counter: TokenCounter, prompt_store: PromptStore):
        self.counter = token_counter
        self.prompt_store = prompt_store
        self._strategies: dict[str, SplitStrategy] = {
            "transcript": TranscriptSplitter(),
            "reasoning": ReasoningSplitter(),
            "summary": SummarySplitter(),
            "annotation": TranscriptSplitter(),
        }

    @staticmethod
    def _hash_prompt(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def split(
        self,
        task: LLMTask,
        chunk_size: int,
        strategy_name: str | None = None,
    ) -> list[LLMTask]:
        """Split task into smaller chunks using appropriate strategy."""
        strategy = self._strategies.get(strategy_name or task.task_type, TranscriptSplitter())

        original_content = self.prompt_store.get(task.prompt_id)
        chunks = strategy.split(original_content, chunk_size, self.counter)

        if len(chunks) <= 1:
            return [task]

        total_input_tokens = sum(self.counter.count(chunk) for chunk in chunks)
        tasks = []
        current_offset = 0

        for i, chunk in enumerate(chunks):
            chunk_tokens = self.counter.count(chunk)
            prompt_id = self.prompt_store.store(chunk, task.job_id, task.task_type)

            proportion = chunk_tokens / max(total_input_tokens, 1)
            chunk_output = max(50, int(task.expected_output_tokens * proportion))

            split_metadata = SplitMetadata(
                original_prompt_id=task.prompt_id,
                chunk_index=i,
                total_chunks=len(chunks),
                start_offset=current_offset,
                end_offset=current_offset + chunk_tokens,
                original_token_count=task.prompt_tokens,
            )

            new_task = LLMTask(
                task_id=generate_task_id(
                    task.job_id,
                    task.stage,
                    self._hash_prompt(chunk),
                    i,
                ),
                task_type=task.task_type,
                priority=task.priority,
                prompt_id=prompt_id,
                prompt_tokens=chunk_tokens,
                expected_output_tokens=chunk_output,
                model_name=task.model_name,
                job_id=task.job_id,
                stage=task.stage,
                split_metadata=split_metadata,
            )

            tasks.append(new_task)
            current_offset += chunk_tokens

        return tasks
