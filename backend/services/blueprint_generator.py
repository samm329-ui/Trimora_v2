from __future__ import annotations

import hashlib
import logging

from backend.config.settings import settings
from backend.models.generation_state import DuplicateRejection, SegmentUsage
from backend.models.semantic import SegmentAnnotations
from backend.models.story import Story
from backend.models.story_blueprint import StoryBlueprint
from backend.services.duplicate_guard import DuplicateGuard
from backend.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class BlueprintGenerator:
    def __init__(self, embedder: EmbeddingService):
        self.embedder = embedder
        self.duplicate_guard = DuplicateGuard(embedder)

    def generate_blueprints(self, validated_stories: list[Story], rejected_stories: list[Story], segments, annotations: SegmentAnnotations):
        from backend.models.generation_state import BlueprintGenerationState

        state = BlueprintGenerationState(job_id=annotations.job_id)
        blueprints: list[StoryBlueprint] = []
        annotation_map = {a.segment_id: a for a in annotations.annotations}
        segment_map = {s.id: s for s in segments}

        for story in validated_stories:
            story_blueprints = self._story_to_blueprints(story, annotation_map, segment_map)
            for bp in story_blueprints:
                is_dup, reason, detail = self.duplicate_guard.is_duplicate(bp, blueprints)
                if is_dup:
                    state.blueprints_rejected_duplicates += 1
                    state.duplicate_rejections.append(DuplicateRejection(
                        blueprint_id=bp.blueprint_id, reason=reason, detail=detail,
                    ))
                    continue
                for sid in bp.segment_ids:
                    if sid not in state.segment_usage:
                        state.segment_usage[sid] = SegmentUsage(segment_id=sid)
                    state.segment_usage[sid].usage_count += 1
                    state.segment_usage[sid].blueprint_ids.append(bp.blueprint_id)
                state.total_blueprints_generated += 1
                blueprints.append(bp)

        blueprints.sort(key=lambda b: b.blueprint_confidence, reverse=True)
        return blueprints, state

    def _story_to_blueprints(self, story: Story, annotation_map: dict, segment_map: dict) -> list[StoryBlueprint]:
        if story.duration <= settings.blueprint_short_max:
            return [self._build_blueprint(story, story.segment_ids, annotation_map, segment_map)]

        blueprints = []
        hook_seg = self._find_best_hook(story, annotation_map)
        ending_seg = self._find_best_ending(story, annotation_map)
        body_segs = [sid for sid in story.segment_ids if sid not in (hook_seg, ending_seg)]

        body_a = self._select_body_window(body_segs, annotation_map, segment_map, max_duration=50)
        bp_a = self._build_blueprint(story, [hook_seg] + body_a + [ending_seg], annotation_map, segment_map)
        bp_a.notes = "Short cut: hook + strongest body section + ending"
        blueprints.append(bp_a)

        body_b = self._select_body_window(body_segs, annotation_map, segment_map, max_duration=50, offset=0.5)
        if body_b != body_a:
            bp_b = self._build_blueprint(story, [hook_seg] + body_b + [ending_seg], annotation_map, segment_map)
            bp_b.notes = "Alternative cut: different body focus"
            blueprints.append(bp_b)

        bp_c = self._build_blueprint(story, story.segment_ids, annotation_map, segment_map)
        bp_c.notes = "Full story: complete narrative arc"
        blueprints.append(bp_c)

        return blueprints

    def _build_blueprint(self, story: Story, segment_ids: list[str], annotation_map: dict, segment_map: dict) -> StoryBlueprint:
        opening_seg_id = segment_ids[0] if segment_ids else ""
        for sid in segment_ids[:3]:
            a = annotation_map.get(sid)
            if a and a.hook_strength > 0.5:
                opening_seg_id = sid
                break

        ending_seg_id = segment_ids[-1] if segment_ids else ""
        for sid in reversed(segment_ids[-3:]):
            a = annotation_map.get(sid)
            if a and a.ending_strength > 0.5:
                ending_seg_id = sid
                break

        cut_timestamps = []
        prev_role = None
        for sid in segment_ids:
            a = annotation_map.get(sid)
            s = segment_map.get(sid)
            if a and s and prev_role and a.story_role != prev_role:
                cut_timestamps.append(s.start)
            if a:
                prev_role = a.story_role

        seg_confidences = [annotation_map[sid].confidence_score for sid in segment_ids if sid in annotation_map]
        cut_confidence = sum(seg_confidences) / max(len(seg_confidences), 1) if seg_confidences else 0.5

        segment_str = "|".join(segment_ids)
        sig = f"{story.story_id}:{hashlib.md5(segment_str.encode()).hexdigest()[:12]}"

        start_time = segment_map[segment_ids[0]].start if segment_ids[0] in segment_map else 0
        end_time = segment_map[segment_ids[-1]].end if segment_ids[-1] in segment_map else 0

        return StoryBlueprint(
            blueprint_id=f"bp_{story.story_id}_{story.version}_{len(segment_ids)}",
            story_id=story.story_id,
            story_name=story.story_name,
            validated_story_summary=story.validated_story_summary,
            segment_ids=segment_ids,
            start_time=start_time,
            end_time=end_time,
            target_duration=story.duration,
            story_arc=self._build_arc(segment_ids, annotation_map),
            opening_segment=opening_seg_id,
            ending_segment=ending_seg_id,
            cut_timestamps=cut_timestamps,
            transition_points=list(cut_timestamps),
            cut_confidence=round(cut_confidence, 4),
            blueprint_confidence=round(story.story_quality_score, 4),
            blueprint_intent=story.content_category or "storytelling",
            blueprint_signature=sig,
        )

    def _find_best_hook(self, story: Story, annotation_map: dict) -> str:
        best_sid = story.segment_ids[0] if story.segment_ids else ""
        best_score = 0.0
        for sid in story.segment_ids:
            a = annotation_map.get(sid)
            if a and a.hook_strength > best_score:
                best_score = a.hook_strength
                best_sid = sid
        return best_sid

    def _find_best_ending(self, story: Story, annotation_map: dict) -> str:
        best_sid = story.segment_ids[-1] if story.segment_ids else ""
        best_score = 0.0
        for sid in story.segment_ids:
            a = annotation_map.get(sid)
            if a and a.ending_strength > best_score:
                best_score = a.ending_strength
                best_sid = sid
        return best_sid

    def _select_body_window(self, body_segs: list[str], annotation_map: dict, segment_map: dict, max_duration: float = 50.0, offset: float = 0.0) -> list[str]:
        if not body_segs:
            return []

        # Score each segment
        scored = []
        for sid in body_segs:
            a = annotation_map.get(sid)
            score = a.importance_score if a else 0.5
            scored.append((sid, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        # Select top segments within duration budget
        start_idx = int(offset * len(scored))
        selected: list[str] = []
        total_dur = 0.0
        for i in range(start_idx, len(scored)):
            sid = scored[i][0]
            s = segment_map.get(sid)
            dur = (s.end - s.start) if s else 0
            if total_dur + dur > max_duration and selected:
                break
            selected.append(sid)
            total_dur += dur

        # Maintain chronological order
        sid_order = {sid: i for i, sid in enumerate(body_segs)}
        selected.sort(key=lambda s: sid_order.get(s, 0))
        return selected

    @staticmethod
    def _build_arc(segment_ids: list[str], annotation_map: dict) -> dict[str, str]:
        arc: dict[str, str] = {}
        for sid in segment_ids:
            a = annotation_map.get(sid)
            if a:
                arc[sid] = a.story_role
        return arc
