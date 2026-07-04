from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.models.topic_block import TopicBlock
from backend.execution.models import (
    ExecutionRequest, ExecutionResult, PromptBuilder, PromptContext,
    RequestPriority, STAGE_SUMMARY,
)
from backend.execution.repository import SegmentRepository
from backend.services.llm_provider import LLMProvider
from backend.services.block_synopsis_generator import BlockSynopsisGenerator

logger = logging.getLogger(__name__)


class SummaryPromptBuilder(PromptBuilder):
    """Builds summary prompts from PromptContext + SegmentRepository."""

    def build(self, ctx: PromptContext, repo: SegmentRepository) -> str:
        block_indices = ctx.extra.get("block_indices", ())
        synopses = ctx.extra.get("synopses", [])
        lines = []
        for idx, synopsis_data in zip(block_indices, synopses):
            block = repo.get_block(idx)
            if block:
                excerpt = synopsis_data.get("representative_excerpt", "")
                lines.append(
                    f"[Block {idx} | {block.start:.1f}-{block.end:.1f}s | "
                    f"{len(block.segments)} segments]\n"
                    f"{synopsis_data.get('synopsis', '')}\n"
                    f"Excerpt: {excerpt}\n"
                )
        blocks_summary = "\n".join(lines)
        return (
            "Analyze these topic blocks from a video transcript.\n\n"
            f"Topic Blocks:\n{blocks_summary}\n\n"
            "Return JSON with:\n"
            "- main_topic: the central theme\n"
            "- major_topics: list of main topics\n"
            "- speaker_intent: what the speaker is trying to achieve\n"
            "- key_arguments: list of main arguments\n"
            "- narrative_arc: how the story flows\n"
            "- key_entities: important people/places/concepts\n"
            "- language: language code (en, hi, etc.)\n"
            "- target_audience: who this is for\n"
            "- overall_tone: educational|debate|storytelling|motivational|interview"
        )


class TranscriptSummarizer:
    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self._prompt_builder = SummaryPromptBuilder()

    def create_request(
        self,
        blocks: list[TopicBlock],
        synopses: list[dict],
        job_id: str,
    ) -> ExecutionRequest:
        """Create a single ExecutionRequest for summary generation."""
        ctx = PromptContext(
            extra={
                "block_indices": tuple(b.original_block_index for b in blocks),
                "synopses": synopses,
            },
        )
        return ExecutionRequest(
            request_id=f"{job_id}_summary",
            prompt_builder=self._prompt_builder,
            prompt_context=ctx,
            stage=STAGE_SUMMARY,
            priority=RequestPriority.CRITICAL,
            metadata={},
        )

    def parse_result(self, result: ExecutionResult) -> dict:
        """Parse a single ExecutionResult into a summary dict."""
        return result.raw_response

    def generate_summary(
        self,
        blocks: list[TopicBlock],
        synopses_path: Path,
    ) -> dict:
        """
        Generate structured summary from topic blocks.
        1 LLM call.

        Input:
        - Block synopses (deterministic)
        - Representative excerpts (most representative segment)
        """
        synopses = BlockSynopsisGenerator.load_synopses(synopses_path)

        blocks_summary = self._format_blocks_for_summary(blocks, synopses)

        prompt = (
            "Analyze these topic blocks from a video transcript.\n\n"
            "Topic Blocks:\n"
            f"{blocks_summary}\n\n"
            "Return JSON with:\n"
            "- main_topic: the central theme\n"
            "- major_topics: list of main topics\n"
            "- speaker_intent: what the speaker is trying to achieve\n"
            "- key_arguments: list of main arguments\n"
            "- narrative_arc: how the story flows\n"
            "- key_entities: important people/places/concepts\n"
            "- language: language code (en, hi, etc.)\n"
            "- target_audience: who this is for\n"
            "- overall_tone: educational|debate|storytelling|motivational|interview"
        )

        response = self.provider.complete(prompt)
        logger.info("Generated summary: main_topic=%s", response.get("main_topic", "unknown"))
        return response

    def _format_blocks_for_summary(self, blocks: list[TopicBlock], synopses: list[dict]) -> str:
        lines: list[str] = []
        for block, synopsis_data in zip(blocks, synopses):
            excerpt = synopsis_data.get("representative_excerpt", "")
            lines.append(
                f"[Block {block.original_block_index} | "
                f"{block.start:.1f}-{block.end:.1f}s | "
                f"{len(block.segments)} segments]\n"
                f"{synopsis_data.get('synopsis', '')}\n"
                f"Excerpt: {excerpt}\n"
            )
        return "\n".join(lines)

    @staticmethod
    def save_summary(summary: dict, path: Path, model: str = "") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 2,
            "model": model,
            "summary": summary,
            "block_synopses_ref": str(path.parent / "block_synopses.json"),
            "block_embeddings_ref": str(path.parent / "block_embeddings.json"),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def load_summary(path: Path) -> dict:
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("summary", {})
