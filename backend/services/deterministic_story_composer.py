"""
Deterministic Story Composer

The composer does not discover knowledge.
The composer reasons over knowledge that has already been extracted.
Its responsibility is editing, not understanding.
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, field

from backend.config.semantic_config import (
    COMPOSER_BEAM_WIDTH,
    COMPOSER_MAX_SEGMENTS,
    COMPOSER_MIN_SCORE,
    COMPOSER_TARGET_DURATION,
    COMPOSER_QUALITY_THRESHOLD,
    COMPOSER_MIN_IMPROVEMENT,
    COMPOSER_MIN_CONFIDENCE,
    COMPOSER_MIN_IMPORTANCE,
    COMPOSER_MAX_REPEATED_ENTITIES,
    COMPOSER_MONOTONE_EMOTION_COUNT,
    COMPOSER_MIN_PROMISE_SUPPORT,
)
from backend.config.weight_profiles import WeightProfile, DEFAULT_PROFILE
from backend.models.semantic import SegmentAnnotation, SegmentAnnotations, LLMStoryBoundary
from backend.models.segment import AtomicSegment

logger = logging.getLogger(__name__)


@dataclass
class EditorState:
    """The editor's current edit."""
    
    # Promise (from hook)
    promise_text: str
    promise_entities: set[str]
    
    # What's been revealed
    revealed_entities: set[str]
    revealed_topics: set[str]
    
    # Story metrics
    narrative_score: float
    value_score: float
    resolution_score: float
    
    # Constraints
    duration_used: float
    duration_budget: float
    segments_used: int
    
    # History (for quality check)
    segment_ids: list[str]
    recent_emotions: list[str]


@dataclass
class BeamState:
    """One possible edit being explored."""
    state: EditorState
    selected: list[str]
    score: float


@dataclass
class ComposerPipeline:
    """Track stories through the composer pipeline.
    
    The composer owns stages 1-3.
    The validator owns stage 4 (tracked separately).
    """
    
    generated: list[str]           # All stories from beam search
    passing_quality: list[str]     # Passed quality gate
    after_dedup: list[str]         # Survived deduplication


@dataclass
class Decision:
    """Record of a segment decision with full trace."""
    segment_id: str
    narrative: float
    value: float
    resolution: float
    total: float
    selected: bool
    reason: str

    # Trace fields (for FULL debug mode)
    beam_index: int = 0
    iteration: int = 0
    candidate_rank: int = 0
    previous_score: float = 0.0
    marginal_gain: float = 0.0
    quality_score: float = 0.0
    temporal_penalty: float = 0.0
    topic_similarity: float = 0.0


class DeterministicStoryComposer:
    """Deterministic story composer using beam search.
    
    Architecture frozen. Weights tunable.
    """
    
    def __init__(self, profile: WeightProfile | None = None):
        self.profile = profile or DEFAULT_PROFILE
        self.decisions: list[Decision] = []
        self.composer_pipeline = ComposerPipeline(generated=[], passing_quality=[], after_dedup=[])
        self.beam_selection_counts: dict[int, int] = {}
        self.beam_expansions: int = 0
        self.total_candidates_evaluated: int = 0
        self.total_candidates_selected: int = 0
        self.stories_removed_by_dedup: int = 0
        self.story_scores: list[float] = []
        self.story_durations: list[float] = []
        self.story_segment_counts: list[int] = []
    
    def compose(
        self,
        all_segments: list[AtomicSegment],
        annotations: SegmentAnnotations,
        summary: dict,
        topic_blocks: list,
    ) -> dict:
        """Main entry point. Returns pass2-compatible format."""
        
        # Reset tracking state
        self.decisions = []
        self.composer_pipeline = ComposerPipeline(generated=[], passing_quality=[], after_dedup=[])
        self.beam_selection_counts = {}
        self.beam_expansions = 0
        self.total_candidates_evaluated = 0
        self.total_candidates_selected = 0
        self.stories_removed_by_dedup = 0
        self.story_scores = []
        self.story_durations = []
        self.story_segment_counts = []
        
        # Build segment lookup
        seg_map = {s.id: s for s in all_segments}
        
        # Extract hooks and endings from annotations
        hooks = [a for a in annotations.annotations if a.hook_strength > 0.7]
        endings = [a for a in annotations.annotations if a.ending_strength > 0.7]
        
        # Build stories for each hook
        stories = []
        for hook in hooks:
            result = self._compose_for_hook(hook, endings, all_segments, annotations, summary)
            if result:
                story_ids, story_health = result
                stories.append({
                    "segment_ids": story_ids,
                    "hook": hook,
                    "story_health": story_health,
                })
                self.composer_pipeline.generated.append(hook.segment_id)
                self.composer_pipeline.passing_quality.append(hook.segment_id)
        
        # Convert to pass2 format
        pass2_result = self._to_pass2_format(stories, annotations)
        
        # Apply deduplication to boundaries
        if pass2_result.get("boundaries"):
            from backend.models.semantic import LLMStoryBoundary
            boundary_objs = [LLMStoryBoundary(**item) for item in pass2_result["boundaries"]]
            deduped = self.deduplicate_boundaries(boundary_objs)
            pass2_result["boundaries"] = [b.model_dump(mode="json") for b in deduped]
            self.composer_pipeline.after_dedup = [str(i) for i in range(len(deduped))]
        
        return pass2_result
    
    def _compose_for_hook(
        self,
        hook: SegmentAnnotation,
        endings: list[SegmentAnnotation],
        all_segments: list[AtomicSegment],
        annotations: SegmentAnnotations,
        summary: dict,
    ) -> tuple[list[str], dict] | None:
        """Compose one story for a given hook. Returns (segment_ids, story_health) or None."""
        
        # Find the actual hook segment for timestamps
        hook_segment = next((s for s in all_segments if s.id == hook.segment_id), None)
        
        initial_state = self._initialize_state(hook, hook_segment)
        beam = [BeamState(state=initial_state, selected=[hook.segment_id], score=0.0)]
        
        iteration = 0
        while beam and beam[0].state.duration_budget > 10 and len(beam[0].selected) < COMPOSER_MAX_SEGMENTS:
            iteration += 1
            candidates = []
            
            for beam_idx, beam_state in enumerate(beam):
                seg_candidates = self._generate_candidates(all_segments, annotations, beam_state.state)
                
                for seg_idx, seg in enumerate(seg_candidates):
                    if seg.segment_id in beam_state.selected:
                        continue
                    
                    self.total_candidates_evaluated += 1
                    
                    # Score with dynamic weights
                    total, narrative, value, resolution = self._evaluate_candidate(
                        seg, beam_state.state, all_segments
                    )
                    
                    # Compute trace values
                    temporal_penalty = self._compute_temporal_penalty(seg, beam_state.state, all_segments)
                    topic_similarity = self._compute_topic_similarity(seg, beam_state.state)
                    
                    if total < COMPOSER_MIN_SCORE:
                        self._log_decision(
                            seg, narrative, value, resolution, total, False, "Below min score",
                            beam_index=beam_idx, iteration=iteration, candidate_rank=seg_idx,
                            previous_score=beam_state.score, marginal_gain=total,
                            temporal_penalty=temporal_penalty, topic_similarity=topic_similarity,
                        )
                        continue
                    
                    new_state = self._copy_state(beam_state.state)
                    actual_seg = next((s for s in all_segments if s.id == seg.segment_id), None)
                    self._update_state(new_state, seg, actual_seg)
                    
                    if not self._check_story_quality(seg, new_state):
                        self._log_decision(
                            seg, narrative, value, resolution, total, False, "Failed quality check",
                            beam_index=beam_idx, iteration=iteration, candidate_rank=seg_idx,
                            previous_score=beam_state.score, marginal_gain=total,
                            temporal_penalty=temporal_penalty, topic_similarity=topic_similarity,
                        )
                        continue
                    
                    self._log_decision(
                        seg, narrative, value, resolution, total, True, "Beam candidate",
                        beam_index=beam_idx, iteration=iteration, candidate_rank=seg_idx,
                        previous_score=beam_state.score, marginal_gain=total,
                        temporal_penalty=temporal_penalty, topic_similarity=topic_similarity,
                    )
                    
                    self.total_candidates_selected += 1
                    self.beam_selection_counts[beam_idx] = self.beam_selection_counts.get(beam_idx, 0) + 1
                    
                    candidates.append(BeamState(
                        state=new_state,
                        selected=beam_state.selected + [seg.segment_id],
                        score=beam_state.score + total,
                    ))
            
            if not candidates:
                break
            
            self.beam_expansions += 1
            
            # Apply diversity penalty
            diversity_penalties = self._compute_beam_diversity(candidates)
            for i, candidate in enumerate(candidates):
                candidate.score *= (1.0 - diversity_penalties[i])
            
            # Check marginal gain
            previous_best = beam[0].score
            candidates.sort(key=lambda b: b.score, reverse=True)
            best_candidate_score = candidates[0].score
            
            if not self._check_marginal_gain(best_candidate_score, previous_best):
                logger.info("Stopping: marginal gain %.3f below threshold", best_candidate_score - previous_best)
                break
            
            beam = candidates[:COMPOSER_BEAM_WIDTH]
        
        # Find best ending
        best_story = None
        best_score = -1
        
        for beam_state in beam:
            ending = self._find_best_ending(beam_state.state, endings, all_segments)
            if ending:
                w_n, w_v, w_r = self.profile.get_dynamic_weights(
                    beam_state.state.duration_used,
                    beam_state.state.duration_budget
                )
                resolution, _, _ = self._score_resolution(ending, beam_state.state)
                story_score = beam_state.score + resolution * w_r
                if story_score > best_score:
                    best_score = story_score
                    best_story = beam_state.selected + [ending.segment_id]
        
        if best_story is None:
            best_story = beam[0].selected if beam else [hook.segment_id]
        
        # Compute story health (experimental)
        story_health = self._compute_story_health(best_story, annotations, beam[0].state)
        
        # Track story metrics
        self.story_scores.append(round(best_score if best_score >= 0 else 0.0, 3))
        total_duration = beam[0].state.duration_used + beam[0].state.duration_budget
        self.story_durations.append(round(total_duration - beam[0].state.duration_budget, 1))
        self.story_segment_counts.append(len(best_story))
        
        return best_story, story_health
    
    def _initialize_state(self, hook: SegmentAnnotation, hook_segment: AtomicSegment | None = None) -> EditorState:
        """Initialize editor state from hook.
        
        Args:
            hook: The hook annotation with semantic data
            hook_segment: The actual segment with timestamps (optional, for duration calculation)
        """
        duration = (hook_segment.end - hook_segment.start) if hook_segment else 5.0
        return EditorState(
            promise_text=f"Hook at {hook_segment.start:.1f}s" if hook_segment else "Hook",
            promise_entities=set(hook.key_entities),
            revealed_entities=set(hook.key_entities),
            revealed_topics={hook.topic},
            narrative_score=1.0,
            value_score=0.0,
            resolution_score=0.0,
            duration_used=duration,
            duration_budget=COMPOSER_TARGET_DURATION - duration,
            segments_used=1,
            segment_ids=[hook.segment_id],
            recent_emotions=[hook.emotion],
        )
    
    def _copy_state(self, state: EditorState) -> EditorState:
        """Create a deep copy of editor state."""
        return EditorState(
            promise_text=state.promise_text,
            promise_entities=state.promise_entities.copy(),
            revealed_entities=state.revealed_entities.copy(),
            revealed_topics=state.revealed_topics.copy(),
            narrative_score=state.narrative_score,
            value_score=state.value_score,
            resolution_score=state.resolution_score,
            duration_used=state.duration_used,
            duration_budget=state.duration_budget,
            segments_used=state.segments_used,
            segment_ids=state.segment_ids.copy(),
            recent_emotions=state.recent_emotions.copy(),
        )
    
    def _update_state(self, state: EditorState, segment: SegmentAnnotation, actual_seg: AtomicSegment | None = None) -> None:
        """Update editor state after adding a segment."""
        state.revealed_entities.update(segment.key_entities)
        state.revealed_topics.add(segment.topic)
        
        duration = (actual_seg.end - actual_seg.start) if actual_seg else 5.0
        state.duration_used += duration
        state.duration_budget -= duration
        state.segments_used += 1
        state.segment_ids.append(segment.segment_id)
        state.recent_emotions.append(segment.emotion)
        
        # Keep only last 5 emotions for variety check
        if len(state.recent_emotions) > 5:
            state.recent_emotions = state.recent_emotions[-5:]
    
    def _generate_candidates(
        self,
        all_segments: list[AtomicSegment],
        annotations: SegmentAnnotations,
        state: EditorState,
    ) -> list[SegmentAnnotation]:
        """Generate every reasonable next edit.
        
        Hard filters (impossible to produce better story):
        - Already selected
        - Exceeds duration budget
        - Invalid timestamps
        - Confidence below minimum
        """
        
        candidates = []
        ann_map = {a.segment_id: a for a in annotations.annotations}
        
        for seg in all_segments:
            # Hard filter: already selected
            if seg.id in state.segment_ids:
                continue
            
            # Hard filter: exceeds duration budget
            duration = seg.end - seg.start
            if duration > state.duration_budget:
                continue
            
            # Hard filter: invalid timestamps
            if seg.start >= seg.end or seg.start < 0:
                continue
            
            # Get annotation
            ann = ann_map.get(seg.id)
            if ann is None:
                continue
            
            # Hard filter: confidence below minimum
            if ann.confidence_score < COMPOSER_MIN_CONFIDENCE:
                continue
            
            # Hard filter: importance below minimum
            if ann.importance_score < COMPOSER_MIN_IMPORTANCE:
                continue
            
            candidates.append(ann)
        
        return candidates
    
    def _evaluate_candidate(
        self,
        segment: SegmentAnnotation,
        state: EditorState,
        all_segments: list[AtomicSegment],
    ) -> tuple[float, float, float, float]:
        """Score candidate with soft penalties applied.
        
        Returns (total, narrative, value, resolution).
        """
        
        # Get dynamic weights
        w_n, w_v, w_r = self.profile.get_dynamic_weights(
            state.duration_used,
            state.duration_budget
        )
        
        # Find actual segment for duration
        actual_seg = next((s for s in all_segments if s.id == segment.segment_id), None)
        
        # Base scores
        narrative = self._score_narrative(segment, state)
        value = self._score_value(segment, state)
        resolution, _, _ = self._score_resolution(segment, state, actual_seg)
        
        # Weighted total
        total = narrative * w_n + value * w_v + resolution * w_r
        
        # Soft penalties (never discard, only reduce)
        
        # Temporal distance penalty
        temporal_penalty = self._compute_temporal_penalty(segment, state, all_segments)
        total *= (1.0 - temporal_penalty)
        
        # Topic mismatch penalty (using semantic similarity)
        topic_sim = self._compute_topic_similarity(segment, state)
        if topic_sim < 0.3:
            total *= 0.8
        
        # Low narrative support penalty
        if narrative < 0.2:
            total *= 0.7
        
        return total, narrative, value, resolution
    
    def _score_narrative(self, segment: SegmentAnnotation, state: EditorState) -> float:
        """Does this belong to the same story?"""
        score = 0.0
        
        # Promise entity alignment
        entity_overlap = len(set(segment.key_entities) & state.promise_entities)
        score += min(1.0, entity_overlap / 2) * self.profile.narrativePromise
        
        # Topic similarity (semantic, not lexical)
        topic_sim = self._compute_topic_similarity(segment, state)
        score += topic_sim * self.profile.narrativeTopic
        
        # Importance as small modifier
        score += segment.importance_score * 0.1 * self.profile.narrativeEntity
        
        return min(1.0, score)
    
    def _score_value(self, segment: SegmentAnnotation, state: EditorState) -> float:
        """Does this improve the edit?"""
        score = 0.0
        
        # Novelty: new entities
        new_entities = len(set(segment.key_entities) - state.revealed_entities)
        novelty = min(1.0, new_entities * 0.3)
        score += novelty * self.profile.valueNovelty
        
        # Curiosity
        score += segment.curiosity_score * self.profile.valueCuriosity
        
        # Emotion: weak modifier
        if segment.emotion not in state.recent_emotions[-2:]:
            score += segment.emotion_intensity * self.profile.valueEmotion
        
        # Importance: small modifier
        score += segment.importance_score * 0.1 * self.profile.valueImportance
        
        return min(1.0, score)
    
    def _score_resolution(self, segment: SegmentAnnotation, state: EditorState, actual_seg: AtomicSegment | None = None) -> tuple[float, float, float]:
        """Does this move toward a satisfying ending?"""
        score = 0.0
        
        # Duration fitness
        segment_duration = (actual_seg.end - actual_seg.start) if actual_seg else 5.0
        fits = 1.0 if segment_duration <= state.duration_budget else 0.2
        score += fits * self.profile.resolutionDuration
        
        # Use ending_strength from annotations
        total = state.duration_used + state.duration_budget
        progress = state.duration_used / total if total > 0 else 0
        if progress > 0.7:
            score += segment.ending_strength * self.profile.resolutionEnding
        
        if progress > 0.6:
            score += segment.ending_strength * self.profile.resolutionSignal
        
        return min(1.0, score), 0.0, 0.0
    
    def _compute_topic_similarity(self, segment: SegmentAnnotation, state: EditorState) -> float:
        """Continuous topic similarity using semantic outputs from Pass 1.
        
        No lexical fallback.
        """
        
        # Direct topic match
        if segment.topic in state.revealed_topics:
            return 1.0
        
        # Subtopic match
        if segment.subtopic and segment.subtopic in state.revealed_topics:
            return 0.8
        
        # Entity cluster overlap
        entity_overlap = len(set(segment.key_entities) & state.revealed_entities)
        if entity_overlap > 0:
            return min(1.0, entity_overlap / 2) * 0.7
        
        # Semantic confidence as fallback
        if segment.confidence_score > 0.8:
            return 0.3
        
        return 0.0
    
    def _compute_temporal_penalty(
        self,
        segment: SegmentAnnotation,
        state: EditorState,
        all_segments: list[AtomicSegment],
    ) -> float:
        """Soft penalty based on temporal distance.
        
        Returns penalty: 0.0 (no penalty) to 0.4 (max penalty).
        Never removes candidate, only reduces score.
        """
        
        if state.segments_used <= 2:
            return 0.0
        
        # Find last selected segment's end time
        last_segment_id = state.segment_ids[-1]
        last_end_time = 0
        for seg in all_segments:
            if seg.id == last_segment_id:
                last_end_time = seg.end
                break
        
        # Find current segment's start time
        actual_seg = next((s for s in all_segments if s.id == segment.segment_id), None)
        if actual_seg is None:
            return 0.0
        
        # Calculate time difference
        time_diff = abs(actual_seg.start - last_end_time)
        
        # Soft penalty curve
        if time_diff < 30:
            return 0.0
        elif time_diff < 60:
            return 0.1
        elif time_diff < 120:
            return 0.2
        elif time_diff < 300:
            return 0.3
        else:
            return 0.4
    
    def _check_story_quality(self, segment: SegmentAnnotation, state: EditorState) -> bool:
        """Does adding this segment improve the overall edit?"""
        quality = 0.0
        
        # Repetition penalty
        repeated = len(set(segment.key_entities) & state.revealed_entities)
        if repeated > COMPOSER_MAX_REPEATED_ENTITIES:
            quality -= 0.3
        
        # Information density
        new_info = len(set(segment.key_entities) - state.revealed_entities)
        if new_info == 0 and state.segments_used > 2:
            quality -= 0.2
        
        # Emotional coherence
        if len(state.recent_emotions) >= COMPOSER_MONOTONE_EMOTION_COUNT:
            last_n = state.recent_emotions[-COMPOSER_MONOTONE_EMOTION_COUNT:]
            if len(set(last_n)) == 1 and segment.emotion == last_n[0]:
                quality -= 0.15
        
        # Promise drift
        promise_support = self._score_narrative(segment, state)
        if promise_support < COMPOSER_MIN_PROMISE_SUPPORT and state.segments_used > 1:
            quality -= 0.2
        
        return quality > COMPOSER_QUALITY_THRESHOLD
    
    def _check_marginal_gain(self, current_score: float, previous_score: float) -> bool:
        """Check if adding next segment provides enough improvement."""
        delta = current_score - previous_score
        return delta >= COMPOSER_MIN_IMPROVEMENT
    
    def _compute_beam_diversity(self, beam_states: list[BeamState]) -> list[float]:
        """Compute diversity penalty for each beam state.
        
        Returns list of penalties (0.0 = no penalty, 1.0 = high penalty).
        """
        
        penalties = []
        
        for i, state_a in enumerate(beam_states):
            max_similarity = 0.0
            
            for j, state_b in enumerate(beam_states):
                if i == j:
                    continue
                
                # Compare selected segments
                set_a = set(state_a.selected)
                set_b = set(state_b.selected)
                
                # Jaccard similarity
                intersection = len(set_a & set_b)
                union = len(set_a | set_b)
                
                if union > 0:
                    similarity = intersection / union
                    max_similarity = max(max_similarity, similarity)
            
            # Penalty increases with similarity
            penalty = max_similarity * 0.3
            penalties.append(penalty)
        
        return penalties
    
    def _compute_selection_entropy(self) -> float:
        """Measure how concentrated the search is.
        
        High entropy: beam explores diverse paths.
        Low entropy: one beam dominates.
        
        Status: Experimental Diagnostic
        """
        
        if not self.beam_selection_counts:
            return 0.0
        
        total = sum(self.beam_selection_counts.values())
        if total == 0:
            return 0.0
        
        entropy = 0.0
        for count in self.beam_selection_counts.values():
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)
        
        return round(entropy, 3)
    
    def _compute_statistics(self) -> dict:
        """Compute statistics the composer owns."""
        
        # Rejection statistics
        rejection_reasons: dict[str, int] = {}
        for d in self.decisions:
            if not d.selected:
                rejection_reasons[d.reason] = rejection_reasons.get(d.reason, 0) + 1
        
        # Per-axis averages for selected segments
        selected_decisions = [d for d in self.decisions if d.selected]
        if selected_decisions:
            avg_narrative = sum(d.narrative for d in selected_decisions) / len(selected_decisions)
            avg_value = sum(d.value for d in selected_decisions) / len(selected_decisions)
            avg_resolution = sum(d.resolution for d in selected_decisions) / len(selected_decisions)
        else:
            avg_narrative = avg_value = avg_resolution = 0.0
        
        # Story composition averages
        avg_story_duration = (
            sum(self.story_durations) / len(self.story_durations)
            if self.story_durations else 0.0
        )
        avg_story_segments = (
            sum(self.story_segment_counts) / len(self.story_segment_counts)
            if self.story_segment_counts else 0.0
        )
        
        # Candidates per step
        avg_candidates_per_step = (
            self.total_candidates_evaluated / max(self.beam_expansions, 1)
        )
        
        return {
            "composer_pipeline": {
                "generated": len(self.composer_pipeline.generated),
                "passing_quality": len(self.composer_pipeline.passing_quality),
                "after_dedup": len(self.composer_pipeline.after_dedup),
            },
            "beam_expansions": self.beam_expansions,
            "average_candidates_per_step": round(avg_candidates_per_step, 1),
            "total_candidates_evaluated": self.total_candidates_evaluated,
            "total_candidates_selected": self.total_candidates_selected,
            "selection_entropy": self._compute_selection_entropy(),
            "average_story_duration": round(avg_story_duration, 1),
            "average_story_segments": round(avg_story_segments, 1),
            "average_narrative_score": round(avg_narrative, 3),
            "average_value_score": round(avg_value, 3),
            "average_resolution_score": round(avg_resolution, 3),
            "rejections": rejection_reasons,
            "stories_removed_by_dedup": self.stories_removed_by_dedup,
        }
    
    def _generate_report(self) -> str:
        """Generate human-readable composer summary."""
        
        stats = self._compute_statistics()
        
        lines = [
            "Composer Summary",
            "=" * 16,
            "",
            "Composer Pipeline:",
            f"  Generated: {stats['composer_pipeline']['generated']}",
            f"  Passing Quality: {stats['composer_pipeline']['passing_quality']}",
            f"  After Dedup: {stats['composer_pipeline']['after_dedup']}",
            "",
            f"Candidates Evaluated: {stats['total_candidates_evaluated']:,}",
            f"Candidates Selected: {stats['total_candidates_selected']}",
            "",
        ]
        
        # Top rejection reasons
        rejections = stats.get("rejections", {})
        if rejections:
            total_rejections = sum(rejections.values())
            lines.append("Top Rejection Reasons:")
            sorted_reasons = sorted(rejections.items(), key=lambda x: x[1], reverse=True)
            for reason, count in sorted_reasons[:5]:
                pct = count / total_rejections * 100 if total_rejections > 0 else 0
                lines.append(f"  {reason}: {count} ({pct:.0f}%)")
            lines.append("")
        
        # Per-axis averages
        lines.append("Per-Axis Averages (Selected):")
        lines.append(f"  Narrative: {stats['average_narrative_score']:.3f}")
        lines.append(f"  Value: {stats['average_value_score']:.3f}")
        lines.append(f"  Resolution: {stats['average_resolution_score']:.3f}")
        lines.append("")
        
        # Diversity
        lines.append("Diversity:")
        lines.append(f"  Selection Entropy: {stats['selection_entropy']:.2f} (Experimental)")
        lines.append(f"  Stories Removed by Dedup: {stats['stories_removed_by_dedup']}")
        lines.append("")
        
        # Story outcomes
        if self.story_scores:
            lines.append("Story Outcomes:")
            for i, (score, dur, segs) in enumerate(
                zip(self.story_scores, self.story_durations, self.story_segment_counts)
            ):
                lines.append(f"  Story {i+1}: Score={score:.2f}, Duration={dur:.1f}s, Segments={segs}")
            lines.append("")
        
        # Runtime
        lines.append("Runtime:")
        lines.append(f"  Beam Expansions: {stats['beam_expansions']}")
        lines.append(f"  Avg Candidates/Step: {stats['average_candidates_per_step']}")
        lines.append("")
        
        lines.append(f"Profile: {self.profile.name}_{self.profile.version}")
        
        return "\n".join(lines)
    
    def deduplicate_boundaries(self, boundaries: list[LLMStoryBoundary]) -> list[LLMStoryBoundary]:
        """Deduplicate by clustering and selecting best representative.
        
        Does NOT merge stories. Preserves alternative edits.
        """
        
        if len(boundaries) <= 1:
            return boundaries
        
        # Build overlap matrix
        overlap_matrix = self._build_overlap_matrix(boundaries)
        
        # Cluster by overlap threshold (40%)
        clusters = self._cluster_by_overlap(boundaries, overlap_matrix, threshold=0.40)
        
        # Select best from each cluster
        selected = []
        for cluster_indices in clusters:
            best_idx = self._select_best_from_cluster(boundaries, cluster_indices)
            selected.append(boundaries[best_idx])
        
        self.stories_removed_by_dedup = len(boundaries) - len(selected)
        return selected
    
    def _build_overlap_matrix(self, boundaries: list[LLMStoryBoundary]) -> list[list[float]]:
        """Build pairwise segment overlap matrix."""
        n = len(boundaries)
        matrix = [[0.0] * n for _ in range(n)]
        
        for i in range(n):
            set_i = set(boundaries[i].boundary_segments)
            for j in range(i + 1, n):
                set_j = set(boundaries[j].boundary_segments)
                intersection = len(set_i & set_j)
                union = len(set_i | set_j)
                overlap = intersection / union if union > 0 else 0.0
                matrix[i][j] = overlap
                matrix[j][i] = overlap
        
        return matrix
    
    def _cluster_by_overlap(
        self,
        boundaries: list[LLMStoryBoundary],
        overlap_matrix: list[list[float]],
        threshold: float = 0.40,
    ) -> list[list[int]]:
        """Cluster boundaries by overlap similarity."""
        n = len(boundaries)
        visited = [False] * n
        clusters = []
        
        for i in range(n):
            if visited[i]:
                continue
            
            cluster = [i]
            visited[i] = True
            
            for j in range(i + 1, n):
                if visited[j]:
                    continue
                
                # Check if j overlaps with any member of the cluster
                if any(overlap_matrix[i][j] >= threshold for i in cluster if i != j):
                    cluster.append(j)
                    visited[j] = True
            
            clusters.append(cluster)
        
        return clusters
    
    def _select_best_from_cluster(
        self,
        boundaries: list[LLMStoryBoundary],
        cluster_indices: list[int],
    ) -> int:
        """Select the best boundary from a cluster based on quality score."""
        best_idx = cluster_indices[0]
        best_score = self._boundary_quality_score(boundaries[best_idx])
        
        for idx in cluster_indices[1:]:
            score = self._boundary_quality_score(boundaries[idx])
            if score > best_score:
                best_score = score
                best_idx = idx
        
        return best_idx
    
    def _boundary_quality_score(self, boundary: LLMStoryBoundary) -> float:
        """Compute quality score for a boundary."""
        
        # Factor 1: Confidence scores
        avg_confidence = (
            boundary.start_confidence +
            boundary.end_confidence +
            boundary.boundary_confidence
        ) / 3
        
        # Factor 2: Segment count (prefer 4-8 segments)
        segment_count = len(boundary.boundary_segments)
        if 4 <= segment_count <= 8:
            segment_score = 1.0
        elif segment_count < 4:
            segment_score = segment_count / 4
        else:
            segment_score = 8 / segment_count
        
        # Factor 3: Structural confidence
        structural_score = boundary.structural_confidence
        
        return avg_confidence * 0.4 + segment_score * 0.3 + structural_score * 0.3
    
    def _find_best_ending(
        self,
        state: EditorState,
        endings: list[SegmentAnnotation],
        all_segments: list[AtomicSegment] | None = None,
    ) -> SegmentAnnotation | None:
        """Find the best ending segment for the current state."""
        
        best_ending = None
        best_score = -1
        
        for ending in endings:
            # Skip if already selected
            if ending.segment_id in state.segment_ids:
                continue
            
            # Check if ending fits
            actual_seg = next((s for s in all_segments if s.id == ending.segment_id), None) if all_segments else None
            ending_duration = (actual_seg.end - actual_seg.start) if actual_seg else 5.0
            if ending_duration > state.duration_budget:
                continue
            
            # Score ending
            resolution, _, _ = self._score_resolution(ending, state, actual_seg)
            
            if resolution > best_score:
                best_score = resolution
                best_ending = ending
        
        return best_ending
    
    def _compute_story_health(
        self,
        selected_ids: list[str],
        annotations: SegmentAnnotations,
        state: EditorState,
    ) -> dict:
        """Compute metrics for evaluation. NOT used in scoring.
        
        Status: Experimental - collect data first, evaluate later.
        """
        
        ann_map = {a.segment_id: a for a in annotations.annotations}
        selected_anns = [ann_map[sid] for sid in selected_ids if sid in ann_map]
        
        if not selected_anns:
            return {}
        
        all_entities = []
        for a in selected_anns:
            all_entities.extend(a.key_entities)
        
        unique_entities = set(all_entities)
        
        return {
            "status": "experimental",
            "total_segments": len(selected_anns),
            "unique_entities": len(unique_entities),
            "repeated_entity_count": len(all_entities) - len(unique_entities),
            "avg_importance": sum(a.importance_score for a in selected_anns) / len(selected_anns),
            "avg_curiosity": sum(a.curiosity_score for a in selected_anns) / len(selected_anns),
            "avg_ending_strength": sum(a.ending_strength for a in selected_anns) / len(selected_anns),
            "unique_emotions": len(set(a.emotion for a in selected_anns)),
            "duration_used": state.duration_used,
            "duration_budget": state.duration_budget,
            "segments_used": state.segments_used,
        }
    
    def _log_decision(
        self,
        segment: SegmentAnnotation,
        narrative: float,
        value: float,
        resolution: float,
        total: float,
        selected: bool,
        reason: str,
        beam_index: int = 0,
        iteration: int = 0,
        candidate_rank: int = 0,
        previous_score: float = 0.0,
        marginal_gain: float = 0.0,
        quality_score: float = 0.0,
        temporal_penalty: float = 0.0,
        topic_similarity: float = 0.0,
    ) -> None:
        """Log segment decision for debugging."""
        
        self.decisions.append(Decision(
            segment_id=segment.segment_id,
            narrative=round(narrative, 3),
            value=round(value, 3),
            resolution=round(resolution, 3),
            total=round(total, 3),
            selected=selected,
            reason=reason,
            beam_index=beam_index,
            iteration=iteration,
            candidate_rank=candidate_rank,
            previous_score=round(previous_score, 3),
            marginal_gain=round(marginal_gain, 3),
            quality_score=round(quality_score, 3),
            temporal_penalty=round(temporal_penalty, 3),
            topic_similarity=round(topic_similarity, 3),
        ))
    
    def _to_pass2_format(
        self,
        stories: list[dict],
        annotations: SegmentAnnotations,
    ) -> dict:
        """Convert stories to pass2-compatible format."""
        
        boundaries = []
        for story in stories:
            segment_ids = story["segment_ids"]
            if not segment_ids:
                continue
            
            boundary = LLMStoryBoundary(
                block_ids=[0],
                boundary_segments=segment_ids,
                story_summary=f"Story with {len(segment_ids)} segments",
                suggested_name=f"Story {len(boundaries) + 1}",
                start_confidence=0.8,
                end_confidence=0.8,
                boundary_confidence=0.8,
                structural_confidence=0.8,
                semantic_confidence=0.8,
                ambiguous_segments=[],
            )
            boundaries.append(boundary)
        
        return {"boundaries": [b.model_dump(mode="json") for b in boundaries]}
    
    def save_reasoning_artifact(
        self,
        job_id: str,
        story_health: dict | None = None,
    ) -> None:
        """Save story_reasoning.json for debugging."""
        
        stats = self._compute_statistics()
        report = self._generate_report()
        
        artifact = {
            "composer_version": "v1",
            "weights_profile": self.profile.name,
            "beam_width": COMPOSER_BEAM_WIDTH,
            "statistics": stats,
            "report": report,
            "decisions": [
                {
                    "segment_id": d.segment_id,
                    "narrative": d.narrative,
                    "value": d.value,
                    "resolution": d.resolution,
                    "total": d.total,
                    "selected": d.selected,
                    "reason": d.reason,
                    "beam_index": d.beam_index,
                    "iteration": d.iteration,
                    "candidate_rank": d.candidate_rank,
                    "previous_score": d.previous_score,
                    "marginal_gain": d.marginal_gain,
                    "quality_score": d.quality_score,
                    "temporal_penalty": d.temporal_penalty,
                    "topic_similarity": d.topic_similarity,
                }
                for d in self.decisions
            ],
            "story_health": story_health or {},
        }
        
        path = f"storage/jobs/{job_id}/stories/story_reasoning.json"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        with open(path, "w") as f:
            json.dump(artifact, f, indent=2)
        
        logger.info("Saved story reasoning artifact: %s", path)
