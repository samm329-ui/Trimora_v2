from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from backend.config.settings import settings
from backend.execution.models import (
    ExecutionRequest, ExecutionResult, PromptBuilder, PromptContext,
    RequestPriority, STAGE_PASS1,
)
from backend.execution.repository import SegmentRepository
from backend.models.semantic import SegmentAnnotation, SegmentRelationship, SegmentAnnotations
from backend.models.topic_block import TopicBlock
from backend.services.llm_provider import LLMProvider

logger = logging.getLogger(__name__)


class SemanticEnrichmentError(Exception):
    """Raised when semantic enrichment fails, carrying partial results."""
    def __init__(self, message: str, partial_annotations: list[SegmentAnnotation], partial_relationships: list[SegmentRelationship], raw_outputs: list[dict], last_batch_index: int):
        super().__init__(message)
        self.partial_annotations = partial_annotations
        self.partial_relationships = partial_relationships
        self.raw_outputs = raw_outputs
        self.last_batch_index = last_batch_index


class SemanticPromptBuilder(PromptBuilder):
    """Builds Pass 1 prompts from PromptContext + SegmentRepository."""

    def build(self, context: PromptContext, repo: SegmentRepository) -> str:
        segments = repo.get_segments(context.segment_ids)
        context_before = repo.get_segments(context.context_before_ids)
        context_after = repo.get_segments(context.context_after_ids)
        segments_text = self._format_segments(segments)
        summary_text = f"Full transcript summary:\n{context.summary}\n\n" if context.summary else ""
        context_text = ""
        if context_before:
            context_text += "Previous context:\n" + self._format_segments(context_before) + "\n\n"
        if context_after:
            context_text += "Following context:\n" + self._format_segments(context_after) + "\n\n"
        return (
            "You are a video content analyst. For each segment below, provide:\n"
            "1. topic and subtopic\n"
            "2. story_role (hook, body, or ending)\n"
            "3. intent (explain, argue, narrate, question, conclude)\n"
            "4. emotion and emotion_intensity (0.0-1.0)\n"
            "5. importance_score (0.0-1.0)\n"
            "6. hook_strength (0.0-1.0) - how strong as an opening\n"
            "7. ending_strength (0.0-1.0) - how strong as a closing\n"
            "8. curiosity_score (0.0-1.0)\n"
            "9. information_density (0.0-1.0)\n"
            "10. key_entities and keywords\n"
            "11. confidence_score (0.0-1.0)\n\n"
            f"{summary_text}{context_text}"
            f"Segments:\n{segments_text}\n\n"
            "Return JSON: {\"annotations\": [...], \"relationships\": [...]}\n"
            "Each annotation must have segment_id matching the segment id."
        )

    @staticmethod
    def _format_segments(segments) -> str:
        return "\n".join(f"[{s.id} | {s.start:.1f}-{s.end:.1f}s] {s.text}" for s in segments)


class SemanticService:
    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self._prompt_builder = SemanticPromptBuilder()

    def create_requests(
        self,
        blocks: list[TopicBlock],
        segments: list,
        summary: str,
        job_id: str,
    ) -> list[ExecutionRequest]:
        """Create ExecutionRequests for Pass 1 — one per block batch."""
        overlap = settings.semantic_context_overlap
        requests = []

        for block in blocks:
            block_segments = block.segments
            if not block_segments:
                continue

            context_before = self._get_previous_context(blocks, block)
            context_after = self._get_next_context(blocks, block)

            for batch_start in range(0, len(block_segments), max(1, settings.semantic_batch_size - overlap)):
                batch_end = min(batch_start + settings.semantic_batch_size, len(block_segments))
                batch = block_segments[batch_start:batch_end]

                block_context_before = block_segments[max(0, batch_start - overlap):batch_start]
                block_context_after = block_segments[batch_end:min(len(block_segments), batch_end + overlap)]

                combined_context_before = (context_before + block_context_before) if context_before else block_context_before
                combined_context_after = (block_context_after + context_after) if context_after else block_context_after

                batch_id = batch_start // max(1, settings.semantic_batch_size - overlap)
                ctx = PromptContext(
                    block_index=block.original_block_index,
                    batch_index=batch_id,
                    segment_ids=tuple(s.id for s in batch),
                    context_before_ids=tuple(s.id for s in combined_context_before),
                    context_after_ids=tuple(s.id for s in combined_context_after),
                    summary=summary,
                )
                requests.append(ExecutionRequest(
                    request_id=f"{job_id}_pass1_b{block.original_block_index}_batch{batch_id}",
                    prompt_builder=self._prompt_builder,
                    prompt_context=ctx,
                    stage=STAGE_PASS1,
                    priority=RequestPriority.HIGH if block.original_block_index < 3 else RequestPriority.NORMAL,
                    metadata={"block_index": block.original_block_index, "batch_id": batch_id},
                ))

        return requests

    def parse_result(self, result: ExecutionResult) -> tuple[list[SegmentAnnotation], list[SegmentRelationship]]:
        """Parse a single ExecutionResult into annotations and relationships."""
        raw = result.raw_response
        annotations = []
        relationships = []
        for item in raw.get("annotations", []):
            annotation = SegmentAnnotation(**item)
            for field in [
                "emotion_intensity", "importance_score", "hook_strength",
                "ending_strength", "curiosity_score", "information_density",
                "standalone_score", "completeness_score", "confidence_score",
            ]:
                val = getattr(annotation, field, 0.5)
                setattr(annotation, field, max(0.0, min(1.0, val)))
            annotations.append(annotation)
        for item in raw.get("relationships", []):
            rel = SegmentRelationship(**item)
            relationships.append(rel)
        return annotations, relationships

    def annotate_segments(
        self,
        segments,
        blocks: list[TopicBlock],
        transcript_text: str,
        job_id: str,
        summary: str = "",
        checkpoint_path: Path | None = None,
        progress_callback=None,
    ) -> tuple[SegmentAnnotations, dict]:
        """
        Annotate segments in TIMELINE ORDER respecting block boundaries.

        Rules:
        - NEVER process in priority order (use timeline order)
        - Never let a batch cross a block boundary
        - Allow context from adjacent blocks (last 2 of previous, first 2 of next)
        """
        all_annotations: list[SegmentAnnotation] = []
        all_relationships: list[SegmentRelationship] = []
        raw_outputs: list[dict] = []
        completed_segment_ids: set[str] = set()

        overlap = settings.semantic_context_overlap

        # Resume from checkpoint if it exists
        if checkpoint_path and checkpoint_path.exists():
            try:
                with open(checkpoint_path, encoding="utf-8") as f:
                    for line in f:
                        entry = json.loads(line.strip())
                        completed_segment_ids.update(entry.get("segment_ids", []))
                        for item in entry.get("annotations", []):
                            all_annotations.append(SegmentAnnotation(**item))
                        for item in entry.get("relationships", []):
                            all_relationships.append(SegmentRelationship(**item))
                        raw_outputs.append(entry.get("raw", {}))
                logger.info("Resumed from checkpoint: %d annotations, %d relationships", len(all_annotations), len(all_relationships))
            except Exception as e:
                logger.warning("Failed to load checkpoint, starting fresh: %s", e)
                completed_segment_ids.clear()
                all_annotations.clear()
                all_relationships.clear()
                raw_outputs.clear()

        # Process blocks in TIMELINE ORDER
        total_batches = 0
        batch_index = 0

        # First pass: count total batches for progress
        for block in blocks:
            block_segments = block.segments
            batch_starts = list(range(0, len(block_segments), max(1, settings.semantic_batch_size - overlap)))
            total_batches += len(batch_starts)

        # Second pass: process blocks in timeline order
        for block in blocks:
            block_segments = block.segments
            if not block_segments:
                continue

            # Get context from adjacent blocks (timeline order)
            context_before = self._get_previous_context(blocks, block)
            context_after = self._get_next_context(blocks, block)

            # Process block with its own batches (never crossing block boundary)
            for batch_start in range(0, len(block_segments), max(1, settings.semantic_batch_size - overlap)):
                batch_end = min(batch_start + settings.semantic_batch_size, len(block_segments))
                batch = block_segments[batch_start:batch_end]

                # Skip batch if all segments already processed
                batch_ids = [s.id for s in batch]
                if all(sid in completed_segment_ids for sid in batch_ids):
                    batch_index += 1
                    if progress_callback:
                        progress_callback(batch_index, total_batches)
                    continue

                # Context within block (not crossing boundary)
                block_context_before = block_segments[max(0, batch_start - overlap):batch_start]
                block_context_after = block_segments[batch_end:min(len(block_segments), batch_end + overlap)]

                # Combine with adjacent block context
                combined_context_before = context_before + block_context_before if context_before else block_context_before
                combined_context_after = block_context_after + context_after if context_after else block_context_after

                prompt = self._build_pass1_prompt(batch, combined_context_before, combined_context_after, summary)

                try:
                    response = self.provider.complete(prompt)
                except Exception as e:
                    logger.error("Batch %d/%d failed (%s): %s",
                                 batch_index + 1, total_batches, type(e).__name__, e)
                    if checkpoint_path:
                        self._save_checkpoint(
                            checkpoint_path, completed_segment_ids,
                            all_annotations, all_relationships, raw_outputs, raw_outputs,
                        )
                    raise SemanticEnrichmentError(
                        f"LLM call failed at batch {batch_index + 1}/{total_batches}: {e}",
                        all_annotations, all_relationships, raw_outputs, batch_index,
                    ) from e

                raw_outputs.append(response)

                batch_annotations = []
                for item in response.get("annotations", []):
                    annotation = SegmentAnnotation(**item)
                    for field in [
                        "emotion_intensity", "importance_score", "hook_strength",
                        "ending_strength", "curiosity_score", "information_density",
                        "standalone_score", "completeness_score", "confidence_score",
                    ]:
                        val = getattr(annotation, field, 0.5)
                        setattr(annotation, field, max(0.0, min(1.0, val)))
                    all_annotations.append(annotation)
                    batch_annotations.append(annotation)
                    completed_segment_ids.add(annotation.segment_id)

                batch_relationships = []
                for item in response.get("relationships", []):
                    rel = SegmentRelationship(**item)
                    all_relationships.append(rel)
                    batch_relationships.append(rel)

                if checkpoint_path:
                    self._save_checkpoint_batch(
                        checkpoint_path, batch_ids,
                        [a.model_dump(mode="json") for a in batch_annotations],
                        [r.model_dump(mode="json") for r in batch_relationships],
                        response,
                    )

                batch_index += 1
                if progress_callback:
                    progress_callback(batch_index, total_batches)

                if settings.semantic_batch_delay_seconds > 0 and batch_index < total_batches:
                    time.sleep(settings.semantic_batch_delay_seconds)

        annotations = SegmentAnnotations(
            job_id=job_id,
            annotations=all_annotations,
            relationships=all_relationships,
        )

        return annotations, {"pass1_raw": raw_outputs}

    def _get_previous_context(self, blocks: list[TopicBlock], current_block: TopicBlock) -> list:
        """Get last 2 segments from previous block (timeline order)."""
        for i, b in enumerate(blocks):
            if b.original_block_index == current_block.original_block_index:
                if i == 0:
                    return []
                return blocks[i - 1].segments[-2:]
        return []

    def _get_next_context(self, blocks: list[TopicBlock], current_block: TopicBlock) -> list:
        """Get first 2 segments from next block (timeline order)."""
        for i, b in enumerate(blocks):
            if b.original_block_index == current_block.original_block_index:
                if i == len(blocks) - 1:
                    return []
                return blocks[i + 1].segments[:2]
        return []

    def _build_pass1_prompt(self, batch, context_before, context_after, summary: str = "") -> str:
        segments_text = self._format_segments(batch)
        summary_text = f"Full transcript summary:\n{summary}\n\n" if summary else ""
        context_text = ""
        if context_before:
            context_text += "Previous context:\n" + self._format_segments(context_before) + "\n\n"
        if context_after:
            context_text += "Following context:\n" + self._format_segments(context_after) + "\n\n"

        return (
            "You are a video content analyst. For each segment below, provide:\n"
            "1. topic and subtopic\n"
            "2. story_role (hook, body, or ending)\n"
            "3. intent (explain, argue, narrate, question, conclude)\n"
            "4. emotion and emotion_intensity (0.0-1.0)\n"
            "5. importance_score (0.0-1.0)\n"
            "6. hook_strength (0.0-1.0) - how strong as an opening\n"
            "7. ending_strength (0.0-1.0) - how strong as a closing\n"
            "8. curiosity_score (0.0-1.0)\n"
            "9. information_density (0.0-1.0)\n"
            "10. key_entities and keywords\n"
            "11. confidence_score (0.0-1.0)\n\n"
            f"{summary_text}"
            f"{context_text}"
            "Segments:\n"
            f"{segments_text}\n\n"
            "Return JSON: {\"annotations\": [...], \"relationships\": [...]}\n"
            "Each annotation must have segment_id matching the segment id."
        )

    @staticmethod
    def _format_segments(segments) -> str:
        lines = []
        for s in segments:
            lines.append(f"[{s.id} | {s.start:.1f}-{s.end:.1f}s] {s.text}")
        return "\n".join(lines)

    @staticmethod
    def _save_checkpoint_batch(
        checkpoint_path: Path,
        segment_ids: list[str],
        annotations_json: list[dict],
        relationships_json: list[dict],
        raw: dict,
    ) -> None:
        """Append one batch entry to the checkpoint file (JSON lines)."""
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "segment_ids": segment_ids,
            "annotations": annotations_json,
            "relationships": relationships_json,
            "raw": raw,
        }
        with open(checkpoint_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @staticmethod
    def _save_checkpoint(
        checkpoint_path: Path | None,
        completed_segment_ids: set[str],
        all_annotations: list[SegmentAnnotation],
        all_relationships: list[SegmentRelationship],
        raw_outputs: list[dict],
        raw_response: list[dict],
    ) -> None:
        """Save full checkpoint (used on error recovery)."""
        if not checkpoint_path:
            return
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "segment_ids": list(completed_segment_ids),
                "annotations": [a.model_dump(mode="json") for a in all_annotations],
                "relationships": [r.model_dump(mode="json") for r in all_relationships],
                "raw": raw_outputs,
            }, ensure_ascii=False) + "\n")
