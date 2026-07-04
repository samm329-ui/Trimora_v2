from __future__ import annotations

import logging

from backend.config.semantic_config import STORY_QUALITY_WEIGHTS, REJECTION_THRESHOLDS
from backend.models.semantic import SegmentAnnotations
from backend.models.story import Story

logger = logging.getLogger(__name__)


class StoryValidator:
    def validate_stories(self, stories: list[Story], rejected_stories: list[Story], segments, annotations: SegmentAnnotations) -> tuple[list[Story], list[Story]]:
        annotation_map = {a.segment_id: a for a in annotations.annotations}
        segment_map = {s.id: s for s in segments}
        validated: list[Story] = []
        all_rejected = list(rejected_stories)

        for story in stories:
            quality = self._compute_quality(story, annotation_map, segment_map)
            story.story_quality_score = quality["composite"]
            story.completeness = quality["completeness"]
            story.coherence = quality["coherence"]
            story.hook_quality = quality["hook_quality"]
            story.ending_quality = quality["ending_quality"]
            story.continuity = quality["continuity"]
            story.emotional_arc = quality["emotional_arc"]
            story.quality_explanation = quality["explanation"]

            rejection = self._check_rejection(story)
            if rejection:
                story.rejection_reason = rejection
                story.rejection_detail = f"Quality: {story.story_quality_score:.2f}. {story.quality_explanation}"
                all_rejected.append(story)
            else:
                story.validated = True
                validated.append(story)

        # Generate validated summaries ONLY for validated stories
        self._generate_validated_summaries(validated, annotations)

        # Assign priority
        validated.sort(key=lambda s: s.story_quality_score, reverse=True)
        for i, story in enumerate(validated):
            story.story_priority = i + 1

        return validated, all_rejected

    def _compute_quality(self, story: Story, annotation_map: dict, segment_map: dict) -> dict:
        story_annotations = [annotation_map.get(sid) for sid in story.segment_ids if sid in annotation_map]

        # Completeness: fraction of segments with annotations
        completeness = len(story_annotations) / max(len(story.segment_ids), 1)

        # Coherence: consistency of topics
        topics = [a.topic for a in story_annotations if a.topic]
        coherence = 1.0 - (len(set(topics)) / max(len(topics), 1)) if topics else 0.5

        # Hook quality
        hook_segs = [a for a in story_annotations if a.story_role == "hook"]
        hook_quality = max((a.hook_strength for a in hook_segs), default=0.5)

        # Ending quality
        ending_segs = [a for a in story_annotations if a.story_role == "ending"]
        ending_quality = max((a.ending_strength for a in ending_segs), default=0.5)

        # Continuity: sequential segment dependencies
        continuity = 0.5
        if len(story_annotations) >= 2:
            deps = sum(1 for a in story_annotations if a.context_dependency != "low")
            continuity = min(1.0, 0.3 + deps / max(len(story_annotations), 1))

        # Emotional arc: variety of emotions
        emotions = [a.emotion for a in story_annotations if a.emotion != "neutral"]
        emotional_arc = min(1.0, len(set(emotions)) / 4.0) if emotions else 0.3

        # Weighted composite
        weights = STORY_QUALITY_WEIGHTS
        composite = (
            weights["completeness"] * completeness
            + weights["coherence"] * coherence
            + weights["hook_quality"] * hook_quality
            + weights["ending_quality"] * ending_quality
            + weights["continuity"] * continuity
            + weights["emotional_arc"] * emotional_arc
        )

        explanation_parts = []
        if completeness < 0.5:
            explanation_parts.append("low completeness")
        if coherence < 0.3:
            explanation_parts.append("low coherence")
        if hook_quality < 0.3:
            explanation_parts.append("weak hook")
        if ending_quality < 0.3:
            explanation_parts.append("weak ending")

        return {
            "composite": round(composite, 4),
            "completeness": round(completeness, 4),
            "coherence": round(coherence, 4),
            "hook_quality": round(hook_quality, 4),
            "ending_quality": round(ending_quality, 4),
            "continuity": round(continuity, 4),
            "emotional_arc": round(emotional_arc, 4),
            "explanation": "; ".join(explanation_parts) if explanation_parts else "acceptable",
        }

    def _check_rejection(self, story: Story) -> str | None:
        thresholds = REJECTION_THRESHOLDS

        if story.story_quality_score < thresholds["quality_too_low"]:
            return "quality_too_low"

        if story.completeness < thresholds["incomplete_arc"]:
            return "incomplete_arc"

        if story.hook_quality < thresholds["weak_hook"]:
            return "weak_hook"

        if story.ending_quality < thresholds["weak_ending"]:
            return "weak_ending"

        return None

    def _generate_validated_summaries(self, stories: list[Story], annotations: SegmentAnnotations) -> None:
        annotation_map = {a.segment_id: a for a in annotations.annotations}
        for story in stories:
            if story.llm_story_summary:
                story.validated_story_summary = story.llm_story_summary
            else:
                texts = []
                for sid in story.segment_ids[:5]:
                    a = annotation_map.get(sid)
                    if a and a.keywords:
                        texts.append(f"{a.topic}: {', '.join(a.keywords[:3])}")
                story.validated_story_summary = ". ".join(texts) + "." if texts else story.story_name
