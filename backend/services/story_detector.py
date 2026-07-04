from __future__ import annotations

import logging

from backend.config.semantic_config import MAX_GAP_BETWEEN_SEGMENTS, TIMESTAMP_OVERLAP_TOLERANCE
from backend.models.generation_state import RepairRecord
from backend.models.semantic import SegmentAnnotations
from backend.models.story import StoryCandidate, Story

logger = logging.getLogger(__name__)


class StoryDetector:
    def form_candidates(self, segments, annotations: SegmentAnnotations) -> list[StoryCandidate]:
        candidates = []
        for i, boundary in enumerate(annotations.llm_story_boundaries):
            seg_ids = [sid for sid in boundary.boundary_segments
                       if any(s.id == sid for s in segments)]
            candidates.append(StoryCandidate(
                candidate_id=f"cand_{i + 1:03d}",
                segment_ids=seg_ids,
                story_name=boundary.suggested_name,
                llm_story_summary=boundary.story_summary,
                start_confidence=boundary.start_confidence,
                end_confidence=boundary.end_confidence,
                boundary_confidence=boundary.boundary_confidence,
                ambiguous_segment_ids=boundary.ambiguous_segments,
            ))
        return candidates

    def verify_candidates(self, candidates: list[StoryCandidate], segments, annotations: SegmentAnnotations) -> list[StoryCandidate]:
        segment_map = {s.id: s for s in segments}
        for candidate in candidates:
            issues: list[str] = []
            segs = [segment_map[sid] for sid in candidate.segment_ids if sid in segment_map]

            # Check for timestamp overlap
            for i in range(1, len(segs)):
                if segs[i].start < segs[i - 1].end - TIMESTAMP_OVERLAP_TOLERANCE:
                    issues.append("timestamp_overlap")
                    break

            # Check for gaps
            for i in range(1, len(segs)):
                gap = segs[i].start - segs[i - 1].end
                if gap > MAX_GAP_BETWEEN_SEGMENTS:
                    issues.append(f"gap_at_{segs[i - 1].id}")

            # Check for duplicate segments
            if len(candidate.segment_ids) != len(set(candidate.segment_ids)):
                issues.append("duplicate_segments")

            # Check minimum segments
            if len(candidate.segment_ids) < 3:
                issues.append("too_few_segments")

            candidate.verification_issues = issues
            candidate.verified = len(issues) == 0
        return candidates

    def repair_candidates(self, candidates: list[StoryCandidate], segments, annotations: SegmentAnnotations) -> tuple[list[Story], list[Story], list[RepairRecord]]:
        segment_map = {s.id: s for s in segments}
        annotation_map = {a.segment_id: a for a in annotations.annotations}
        repaired_all: list[Story] = []
        rejected_all: list[Story] = []
        repair_records: list[RepairRecord] = []

        for candidate in candidates:
            if candidate.verified:
                story = self._candidate_to_story(candidate, version=1)
                repaired_all.append(story)
                continue

            segs = [segment_map[sid] for sid in candidate.segment_ids if sid in segment_map]
            repaired_segs, actions = self._repair(segs, candidate.verification_issues, segments, annotation_map)

            if repaired_segs is None:
                story = self._candidate_to_story(candidate, version=1)
                story.rejection_reason = candidate.verification_issues[0] if candidate.verification_issues else "unrepairable"
                story.rejection_detail = f"Issues: {', '.join(candidate.verification_issues)}. Repair failed."
                rejected_all.append(story)
                repair_records.append(RepairRecord(
                    candidate_id=candidate.candidate_id,
                    original_issues=candidate.verification_issues,
                    repair_actions=[],
                    success=False,
                ))
            else:
                story = self._candidate_to_story(candidate, version=2)
                story.segment_ids = [s.id for s in repaired_segs]
                story.repair_actions = actions
                repaired_all.append(story)
                repair_records.append(RepairRecord(
                    candidate_id=candidate.candidate_id,
                    original_issues=candidate.verification_issues,
                    repair_actions=actions,
                    success=True,
                ))

        return repaired_all, rejected_all, repair_records

    def _repair(self, segments, issues, all_segments, annotation_map):
        repaired = list(segments)
        actions: list[str] = []
        for issue in issues:
            if issue.startswith("gap_at_"):
                filled = self._fill_gap(repaired, issue, all_segments, annotation_map)
                if filled:
                    repaired = filled
                    actions.append(f"filled_gap_{issue}")
            elif issue == "duplicate_segments":
                seen: set[str] = set()
                before = len(repaired)
                repaired = [s for s in repaired if s.id not in seen and not seen.add(s.id)]
                if len(repaired) < before:
                    actions.append(f"removed_{before - len(repaired)}_duplicates")
            elif issue == "timestamp_overlap":
                repaired = self._resolve_overlap(repaired, annotation_map)
                actions.append("resolved_overlap")
        return (repaired, actions) if len(repaired) >= 3 else (None, [])

    def _fill_gap(self, repaired, issue, all_segments, annotation_map):
        gap_seg_id = issue.replace("gap_at_", "")
        segment_map = {s.id: s for s in all_segments}
        gap_seg = segment_map.get(gap_seg_id)
        if gap_seg is None:
            return repaired

        idx = next((i for i, s in enumerate(repaired) if s.id == gap_seg_id), None)
        if idx is None or idx + 1 >= len(repaired):
            return repaired

        next_seg = repaired[idx + 1]
        candidates = [
            s for s in all_segments
            if s.id not in {rs.id for rs in repaired}
            and gap_seg.end <= s.start <= next_seg.start
            and s.end <= next_seg.start
        ]
        if candidates:
            best = max(candidates, key=lambda s: annotation_map.get(s.id, None).importance_score if annotation_map.get(s.id) else 0.5)
            repaired.insert(idx + 1, best)
        return repaired

    def _resolve_overlap(self, segments, annotation_map):
        if len(segments) < 2:
            return segments
        result = [segments[0]]
        for i in range(1, len(segments)):
            current = segments[i]
            prev = result[-1]
            if current.start < prev.end - TIMESTAMP_OVERLAP_TOLERANCE:
                curr_ann = annotation_map.get(current.id)
                prev_ann = annotation_map.get(prev.id)
                curr_score = curr_ann.importance_score if curr_ann else 0.5
                prev_score = prev_ann.importance_score if prev_ann else 0.5
                if curr_score > prev_score:
                    result[-1] = current
            else:
                result.append(current)
        return result

    def _candidate_to_story(self, candidate: StoryCandidate, version: int = 1) -> Story:
        return Story(
            story_id=f"story_{candidate.candidate_id.replace('cand_', '')}",
            story_name=candidate.story_name,
            version=version,
            llm_story_summary=candidate.llm_story_summary,
            main_message=candidate.main_message,
            audience=candidate.audience,
            content_category=candidate.content_category,
            difficulty=candidate.difficulty,
            segment_ids=list(candidate.segment_ids),
            ambiguous_segment_ids=list(candidate.ambiguous_segment_ids),
            segment_count=len(candidate.segment_ids),
            confidence_score=candidate.boundary_confidence,
        )
