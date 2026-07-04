from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from backend.config.settings import settings
from backend.execution.models import (
    ExecutionRequest, ExecutionResult, PromptBuilder, PromptContext,
    RequestPriority, STAGE_PASS2,
)
from backend.execution.repository import SegmentRepository
from backend.models.semantic import LLMStoryBoundary
from backend.models.topic_block import TopicBlock
from backend.services.llm_provider import LLMProvider

logger = logging.getLogger(__name__)

PASS2_MAX_RETRIES = 3


class Pass2Error(Exception):
    """Raised when Pass 2 fails, carrying partial results."""
    def __init__(self, message: str, partial_boundaries: list[LLMStoryBoundary], raw_outputs: list[dict], last_block_index: int):
        super().__init__(message)
        self.partial_boundaries = partial_boundaries
        self.raw_outputs = raw_outputs
        self.last_block_index = last_block_index


class StoryPromptBuilder(PromptBuilder):
    """Builds Pass 2 prompts from PromptContext + SegmentRepository."""

    def build(self, ctx: PromptContext, repo: SegmentRepository) -> str:
        segments = repo.get_segments(ctx.segment_ids)
        block = repo.get_block(ctx.block_index)
        block_annotations = repo.get_annotations(ctx.segment_ids)

        ann_text = "\n".join(
            f"[{a.segment_id}] role={a.story_role}, topic={a.topic}, "
            f"emotion={a.emotion}({a.emotion_intensity:.1f}), "
            f"importance={a.importance_score:.2f}, hook={a.hook_strength:.2f}, "
            f"ending={a.ending_strength:.2f}, curiosity={a.curiosity_score:.2f}"
            for a in block_annotations
        )
        seg_text = "\n".join(f"[{s.id} | {s.start:.1f}-{s.end:.1f}] {s.text[:80]}" for s in segments)

        prompt = "You are a story editor. Identify distinct stories in the following topic block.\n\n"
        if ctx.summary:
            prompt += f"Video Summary:\n{ctx.summary}\n\n"

        block_synopsis = ctx.extra.get("synopsis", "")
        structural_confidence = ctx.extra.get("structural_confidence", 0.5)
        prompt += f"Current Block #{ctx.block_index} (structural confidence: {structural_confidence:.2f}):\n"
        prompt += f"Synopsis: {block_synopsis}\n\n"

        prev_segs = repo.get_segments(ctx.context_before_ids)
        if prev_segs:
            prev_text = "\n".join(f"[{s.id} | {s.start:.1f}-{s.end:.1f}] {s.text[:80]}" for s in prev_segs)
            prompt += f"Previous block context (for continuity only, do NOT include in stories):\n{prev_text}\n\n"

        prompt += f"Block Segments:\n{seg_text}\n\n"

        next_segs = repo.get_segments(ctx.context_after_ids)
        if next_segs:
            next_text = "\n".join(f"[{s.id} | {s.start:.1f}-{s.end:.1f}] {s.text[:80]}" for s in next_segs)
            prompt += f"Next block context (for continuity only, do NOT include in stories):\n{next_text}\n\n"

        prompt += f"Segment Annotations:\n{ann_text}\n\n"
        prompt += (
            "For each story, provide:\n"
            "1. boundary_segments: list of segment IDs that belong to this story (in order)\n"
            "2. story_summary: a 1-2 sentence summary\n"
            "3. suggested_name: a short, compelling name\n"
            "4. start_confidence, end_confidence, boundary_confidence (0.0-1.0)\n"
            "5. ambiguous_segments: segment IDs where boundaries are uncertain\n\n"
            "Rules:\n"
            "- Each story should have at least 2 segments\n"
            "- Stories should be semantically coherent\n"
            "- A segment can only belong to one story\n"
            "- NEVER include context segments in stories\n"
            "- Mark uncertain boundaries in ambiguous_segments\n\n"
            "Return JSON: {\"stories\": [...]}"
        )
        return prompt


class StoryReasoner:
    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self._prompt_builder = StoryPromptBuilder()

    def create_requests(
        self,
        blocks: list[TopicBlock],
        segments: list,
        annotations,  # SegmentAnnotations
        summary: str,
        job_id: str,
    ) -> list[ExecutionRequest]:
        """Create ExecutionRequests for Pass 2 — one per block."""
        requests = []
        for i, block in enumerate(blocks):
            block_seg_ids = tuple(s.id for s in block.segments)
            prev_ids = tuple(s.id for s in blocks[i - 1].segments[-2:]) if i > 0 else ()
            next_ids = tuple(s.id for s in blocks[i + 1].segments[:2]) if i < len(blocks) - 1 else ()
            ctx = PromptContext(
                block_index=i,
                segment_ids=block_seg_ids,
                context_before_ids=prev_ids,
                context_after_ids=next_ids,
                summary=summary,
                extra={
                    "synopsis": block.synopsis,
                    "structural_confidence": block.structural_confidence,
                },
            )
            requests.append(ExecutionRequest(
                request_id=f"{job_id}_pass2_block{i}",
                prompt_builder=self._prompt_builder,
                prompt_context=ctx,
                stage=STAGE_PASS2,
                priority=RequestPriority.NORMAL if i < 3 else RequestPriority.LOW,
                metadata={"block_index": i},
            ))
        return requests

    def parse_result(self, result: ExecutionResult) -> list[LLMStoryBoundary]:
        """Parse a single ExecutionResult into LLMStoryBoundary list."""
        raw = result.raw_response
        boundaries = []
        for item in raw.get("stories", []):
            boundaries.append(LLMStoryBoundary(
                block_ids=[item.get("block_id", 0)],
                boundary_segments=item.get("boundary_segments", []),
                story_summary=item.get("story_summary", ""),
                suggested_name=item.get("suggested_name", ""),
                start_confidence=item.get("start_confidence", 0.5),
                end_confidence=item.get("end_confidence", 0.5),
                boundary_confidence=item.get("boundary_confidence", 0.5),
                structural_confidence=item.get("structural_confidence", 0.5),
                semantic_confidence=item.get("boundary_confidence", 0.5),
                ambiguous_segments=item.get("ambiguous_segments", []),
            ))
        return boundaries

    def detect_story_boundaries(
        self,
        segments,
        annotations,
        blocks: list[TopicBlock] | None = None,
        summary: str = "",
        checkpoint_path: Path | None = None,
        progress_callback=None,
    ) -> tuple[list[LLMStoryBoundary], dict]:
        all_boundaries: list[LLMStoryBoundary] = []
        raw_outputs: list[dict] = []
        completed_block_indices: set[int] = set()

        # Resume from checkpoint
        if checkpoint_path and checkpoint_path.exists():
            try:
                with open(checkpoint_path, encoding="utf-8") as f:
                    for line in f:
                        entry = json.loads(line.strip())
                        block_idx = entry.get("block_index", -1)
                        completed_block_indices.add(block_idx)
                        for item in entry.get("boundaries", []):
                            all_boundaries.append(LLMStoryBoundary(**item))
                        raw_outputs.append(entry.get("raw", {}))
                logger.info("Pass 2 resumed from checkpoint: %d boundaries, %d blocks done",
                            len(all_boundaries), len(completed_block_indices))
            except Exception as e:
                logger.warning("Failed to load Pass 2 checkpoint, starting fresh: %s", e)
                completed_block_indices.clear()
                all_boundaries.clear()
                raw_outputs.clear()

        if not blocks:
            logger.warning("No blocks provided for Pass 2, returning empty boundaries")
            return [], {"pass2_raw": []}

        total_blocks = len(blocks)

        for block_idx, block in enumerate(blocks):
            if block_idx in completed_block_indices:
                if progress_callback:
                    progress_callback(block_idx + 1, total_blocks)
                continue

            # Collect segment IDs in this block
            block_seg_ids = [s.id for s in block.segments]

            # Collect adjacent context segments (max 2 from each side)
            prev_context_segs = []
            if block_idx > 0:
                prev_block = blocks[block_idx - 1]
                prev_context_segs = prev_block.segments[-2:]

            next_context_segs = []
            if block_idx < len(blocks) - 1:
                next_block = blocks[block_idx + 1]
                next_context_segs = next_block.segments[:2]

            # Build annotations subset for this block
            all_segs_in_prompt = prev_context_segs + block.segments + next_context_segs
            all_segs_in_prompt_ids = {s.id for s in all_segs_in_prompt}
            block_annotations = type(annotations)(
                job_id=annotations.job_id,
                annotations=[a for a in annotations.annotations if a.segment_id in all_segs_in_prompt_ids],
                relationships=[r for r in annotations.relationships
                               if r.source_id in all_segs_in_prompt_ids or r.target_id in all_segs_in_prompt_ids],
            )

            prompt = self._build_pass2_prompt(
                block.segments, block_annotations, summary,
                prev_context_segs, next_context_segs,
                block.synopsis, block.original_block_index,
                block.structural_confidence,
            )

            try:
                response = self.provider.complete(prompt)
            except Exception as e:
                logger.error("Pass 2 block %d/%d failed (%s): %s",
                             block_idx + 1, total_blocks, type(e).__name__, e)
                self._save_checkpoint(
                    checkpoint_path, completed_block_indices,
                    all_boundaries, raw_outputs,
                )
                raise Pass2Error(
                    f"Pass 2 LLM call failed at block {block_idx + 1}/{total_blocks}: {e}",
                    all_boundaries, raw_outputs, block_idx,
                ) from e

            raw_outputs.append(response)

            block_boundaries = []
            for item in response.get("stories", []):
                boundary = LLMStoryBoundary(
                    block_ids=[block.original_block_index],
                    boundary_segments=item.get("boundary_segments", []),
                    story_summary=item.get("story_summary", ""),
                    suggested_name=item.get("suggested_name", ""),
                    start_confidence=item.get("start_confidence", 0.5),
                    end_confidence=item.get("end_confidence", 0.5),
                    boundary_confidence=item.get("boundary_confidence", 0.5),
                    structural_confidence=block.structural_confidence,
                    semantic_confidence=item.get("boundary_confidence", 0.5),
                    ambiguous_segments=item.get("ambiguous_segments", []),
                )
                all_boundaries.append(boundary)
                block_boundaries.append(boundary)

            completed_block_indices.add(block_idx)

            if checkpoint_path:
                self._save_checkpoint_batch(
                    checkpoint_path, block_idx,
                    [b.model_dump(mode="json") for b in block_boundaries],
                    response,
                )

            if progress_callback:
                progress_callback(block_idx + 1, total_blocks)

            # Rate-limit delay between blocks
            if settings.semantic_batch_delay_seconds > 0 and block_idx < total_blocks - 1:
                time.sleep(settings.semantic_batch_delay_seconds)

        # Merge boundaries that overlap across blocks
        merged = self._merge_boundaries(all_boundaries, segments)

        return merged, {"pass2_raw": raw_outputs}

    @staticmethod
    def _merge_boundaries(
        boundaries: list[LLMStoryBoundary],
        segments,
    ) -> list[LLMStoryBoundary]:
        """Merge stories that share segments or are adjacent with same topic."""
        if not boundaries:
            return boundaries

        seg_index = {s.id: i for i, s in enumerate(segments)}
        merged: list[LLMStoryBoundary] = []
        used: set[int] = set()

        for i, b1 in enumerate(boundaries):
            if i in used:
                continue
            current = b1
            used.add(i)

            for j, b2 in enumerate(boundaries):
                if j in used:
                    continue
                s1 = set(current.boundary_segments)
                s2 = set(b2.boundary_segments)
                if s1 & s2:
                    current = LLMStoryBoundary(
                        block_ids=list(dict.fromkeys(current.block_ids + b2.block_ids)),
                        boundary_segments=list(dict.fromkeys(current.boundary_segments + b2.boundary_segments)),
                        story_summary=current.story_summary or b2.story_summary,
                        suggested_name=current.suggested_name or b2.suggested_name,
                        start_confidence=min(current.start_confidence, b2.start_confidence),
                        end_confidence=min(current.end_confidence, b2.end_confidence),
                        boundary_confidence=(current.boundary_confidence + b2.boundary_confidence) / 2,
                        structural_confidence=(current.structural_confidence + b2.structural_confidence) / 2,
                        semantic_confidence=(current.semantic_confidence + b2.semantic_confidence) / 2,
                        ambiguous_segments=list(set(current.ambiguous_segments + b2.ambiguous_segments)),
                    )
                    used.add(j)
                else:
                    if current.boundary_segments and b2.boundary_segments:
                        last_idx = seg_index.get(current.boundary_segments[-1], -1)
                        first_idx = seg_index.get(b2.boundary_segments[0], -1)
                        if last_idx >= 0 and first_idx >= 0 and first_idx == last_idx + 1:
                            current = LLMStoryBoundary(
                                block_ids=list(dict.fromkeys(current.block_ids + b2.block_ids)),
                                boundary_segments=current.boundary_segments + b2.boundary_segments,
                                story_summary=current.story_summary or b2.story_summary,
                                suggested_name=current.suggested_name or b2.suggested_name,
                                start_confidence=current.start_confidence,
                                end_confidence=b2.end_confidence,
                                boundary_confidence=(current.boundary_confidence + b2.boundary_confidence) / 2,
                                structural_confidence=(current.structural_confidence + b2.structural_confidence) / 2,
                                semantic_confidence=(current.semantic_confidence + b2.semantic_confidence) / 2,
                                ambiguous_segments=list(set(current.ambiguous_segments + b2.ambiguous_segments)),
                            )
                            used.add(j)

            merged.append(current)

        return merged

    def _build_pass2_prompt(
        self,
        block_segments,
        annotations,
        summary: str,
        prev_context_segs,
        next_context_segs,
        block_synopsis: str,
        block_index: int,
        structural_confidence: float,
    ) -> str:
        ann_text = self._format_annotations(annotations)
        seg_text = self._format_segments_with_timestamps(block_segments)
        prev_text = self._format_segments_with_timestamps(prev_context_segs) if prev_context_segs else ""
        next_text = self._format_segments_with_timestamps(next_context_segs) if next_context_segs else ""

        prompt = (
            "You are a story editor. Identify distinct stories in the following topic block.\n\n"
        )

        if summary:
            prompt += (
                f"Video Summary:\n{summary}\n\n"
            )

        prompt += (
            f"Current Block #{block_index} (structural confidence: {structural_confidence:.2f}):\n"
            f"Synopsis: {block_synopsis}\n\n"
        )

        if prev_text:
            prompt += f"Previous block context (for continuity only, do NOT include in stories):\n{prev_text}\n\n"

        prompt += (
            f"Block Segments:\n{seg_text}\n\n"
        )

        if next_text:
            prompt += f"Next block context (for continuity only, do NOT include in stories):\n{next_text}\n\n"

        prompt += (
            f"Segment Annotations:\n{ann_text}\n\n"
            "For each story, provide:\n"
            "1. boundary_segments: list of segment IDs that belong to this story (in order)\n"
            "2. story_summary: a 1-2 sentence summary\n"
            "3. suggested_name: a short, compelling name\n"
            "4. start_confidence, end_confidence, boundary_confidence (0.0-1.0)\n"
            "5. ambiguous_segments: segment IDs where boundaries are uncertain\n\n"
            "Rules:\n"
            "- Each story should have at least 2 segments\n"
            "- Stories should be semantically coherent\n"
            "- A segment can only belong to one story\n"
            "- NEVER include context segments in stories\n"
            "- Mark uncertain boundaries in ambiguous_segments\n\n"
            "Return JSON: {\"stories\": [...]}"
        )

        return prompt

    @staticmethod
    def _format_annotations(annotations) -> str:
        lines = []
        for a in annotations.annotations:
            lines.append(
                f"[{a.segment_id}] role={a.story_role}, topic={a.topic}, "
                f"emotion={a.emotion}({a.emotion_intensity:.1f}), "
                f"importance={a.importance_score:.2f}, hook={a.hook_strength:.2f}, "
                f"ending={a.ending_strength:.2f}, curiosity={a.curiosity_score:.2f}"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_segments_with_timestamps(segments) -> str:
        lines = []
        for s in segments:
            lines.append(f"[{s.id} | {s.start:.1f}-{s.end:.1f}] {s.text[:80]}")
        return "\n".join(lines)

    @staticmethod
    def _save_checkpoint_batch(
        checkpoint_path: Path,
        block_index: int,
        boundaries_json: list[dict],
        raw: dict,
    ) -> None:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "block_index": block_index,
            "boundaries": boundaries_json,
            "raw": raw,
        }
        with open(checkpoint_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @staticmethod
    def _save_checkpoint(
        checkpoint_path: Path | None,
        completed_block_indices: set[int],
        all_boundaries: list[LLMStoryBoundary],
        raw_outputs: list[dict],
    ) -> None:
        if not checkpoint_path:
            return
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            for i, block_idx in enumerate(sorted(completed_block_indices)):
                entry = {
                    "block_index": block_idx,
                    "boundaries": [b.model_dump(mode="json") for b in all_boundaries],
                    "raw": raw_outputs[i] if i < len(raw_outputs) else {},
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
