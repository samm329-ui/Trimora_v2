from __future__ import annotations

import hashlib
import logging

from backend.execution.models import LLMTask, TaskPriority, generate_task_id
from backend.execution.repository import SegmentRepository
from backend.models.topic_block import TopicBlock
from backend.services.prompt_store import PromptStore
from backend.services.semantic_service import SemanticService
from backend.services.story_reasoner import StoryReasoner
from backend.services.token_counter import TokenCounter
from backend.services.transcript_summarizer import TranscriptSummarizer

logger = logging.getLogger(__name__)


class PromptFactory:
    """Builds LLMTasks from business logic. Lives outside scheduler."""

    def __init__(
        self,
        semantic_service: SemanticService,
        story_reasoner: StoryReasoner,
        summarizer: TranscriptSummarizer,
        token_counter: TokenCounter,
        prompt_store: PromptStore,
        repo: SegmentRepository,
        model_name: str = "llama-3.1-8b-instant",
    ):
        self.semantic = semantic_service
        self.reasoner = story_reasoner
        self.summarizer = summarizer
        self.counter = token_counter
        self.store = prompt_store
        self.repo = repo
        self.model_name = model_name

    @staticmethod
    def _hash_prompt(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def create_summary_task(
        self,
        blocks: list[TopicBlock],
        synopses: list[dict],
        job_id: str,
    ) -> LLMTask:
        """Create a summary LLMTask."""
        ctx = self.summarizer._prompt_builder._build_context(blocks, synopses) if hasattr(self.summarizer._prompt_builder, '_build_context') else None

        request = self.summarizer.create_request(blocks, synopses, job_id)
        prompt = self.summarizer._prompt_builder.build(request.prompt_context, self.repo)

        prompt_tokens = self.counter.count(prompt)
        prompt_id = self.store.store(prompt, job_id, "summary")

        return LLMTask(
            task_id=generate_task_id(job_id, "summary", self._hash_prompt(prompt)),
            task_type="summary",
            priority=TaskPriority.CRITICAL,
            prompt_id=prompt_id,
            prompt_tokens=prompt_tokens,
            expected_output_tokens=500,
            model_name=self.model_name,
            job_id=job_id,
            stage="summary",
        )

    def create_annotation_tasks(
        self,
        blocks: list[TopicBlock],
        summary_text: str,
        job_id: str,
    ) -> list[LLMTask]:
        """Create Pass 1 annotation LLMTasks."""
        requests = self.semantic.create_requests(blocks, [], summary=summary_text, job_id=job_id)
        tasks = []

        for i, request in enumerate(requests):
            prompt = self.semantic._prompt_builder.build(request.prompt_context, self.repo)
            prompt_tokens = self.counter.count(prompt)
            prompt_id = self.store.store(prompt, job_id, "annotation")

            tasks.append(LLMTask(
                task_id=generate_task_id(job_id, "pass1", self._hash_prompt(prompt), i),
                task_type="annotation",
                priority=TaskPriority.HIGH if i < 3 else TaskPriority.NORMAL,
                prompt_id=prompt_id,
                prompt_tokens=prompt_tokens,
                expected_output_tokens=800,
                model_name=self.model_name,
                job_id=job_id,
                stage="pass1",
            ))

        return tasks

    def create_reasoning_tasks(
        self,
        blocks: list[TopicBlock],
        summary_text: str,
        job_id: str,
    ) -> list[LLMTask]:
        """Create Pass 2 reasoning LLMTasks."""
        requests = self.reasoner.create_requests(blocks, [], None, summary_text, job_id)
        tasks = []

        for i, request in enumerate(requests):
            prompt = self.reasoner._prompt_builder.build(request.prompt_context, self.repo)
            prompt_tokens = self.counter.count(prompt)
            prompt_id = self.store.store(prompt, job_id, "reasoning")

            tasks.append(LLMTask(
                task_id=generate_task_id(job_id, "pass2", self._hash_prompt(prompt), i),
                task_type="reasoning",
                priority=TaskPriority.NORMAL if i < 3 else TaskPriority.LOW,
                prompt_id=prompt_id,
                prompt_tokens=prompt_tokens,
                expected_output_tokens=600,
                model_name=self.model_name,
                job_id=job_id,
                stage="pass2",
            ))

        return tasks
