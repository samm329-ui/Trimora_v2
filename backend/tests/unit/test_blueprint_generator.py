import pytest
from backend.services.blueprint_generator import BlueprintGenerator
from backend.services.duplicate_guard import DuplicateGuard
from backend.services.embedding_service import EmbeddingService
from backend.models.semantic import SegmentAnnotations, SegmentAnnotation
from backend.models.story import Story
from backend.models.story_blueprint import StoryBlueprint
from backend.tests.fixtures.sample_video import make_segments


def _make_annotations():
    annotations = [
        SegmentAnnotation(segment_id="seg_h_0", topic="productivity", story_role="hook", hook_strength=0.9, importance_score=0.8, confidence_score=0.85),
        SegmentAnnotation(segment_id="seg_b_0", topic="productivity", story_role="body", importance_score=0.7, confidence_score=0.8),
        SegmentAnnotation(segment_id="seg_b_1", topic="deep work", story_role="body", importance_score=0.85, confidence_score=0.85),
        SegmentAnnotation(segment_id="seg_b_2", topic="deep work", story_role="body", importance_score=0.75, confidence_score=0.8),
        SegmentAnnotation(segment_id="seg_b_3", topic="distractions", story_role="body", importance_score=0.8, confidence_score=0.82),
        SegmentAnnotation(segment_id="seg_b_4", topic="focus", story_role="body", importance_score=0.65, confidence_score=0.78),
        SegmentAnnotation(segment_id="seg_e_0", topic="deep work", story_role="ending", ending_strength=0.8, importance_score=0.7, confidence_score=0.75),
        SegmentAnnotation(segment_id="seg_e_1", topic="productivity", story_role="ending", ending_strength=0.6, importance_score=0.5, confidence_score=0.7),
    ]
    return SegmentAnnotations(job_id="job_1", annotations=annotations, relationships=[])


def _make_story():
    return Story(
        story_id="story_001",
        story_name="Deep Work",
        segment_ids=["seg_h_0", "seg_b_0", "seg_b_1", "seg_b_2", "seg_e_0"],
        validated_story_summary="Deep work matters for productivity",
        story_quality_score=0.75,
        duration=30.0,
    )


def test_generate_blueprints():
    segments = make_segments()
    annotations = _make_annotations()
    story = _make_story()
    embedder = EmbeddingService()
    gen = BlueprintGenerator(embedder)
    blueprints, state = gen.generate_blueprints([story], [], segments, annotations)
    assert len(blueprints) >= 1
    assert state.total_blueprints_generated >= 1


def test_blueprints_have_signatures():
    segments = make_segments()
    annotations = _make_annotations()
    story = _make_story()
    embedder = EmbeddingService()
    gen = BlueprintGenerator(embedder)
    blueprints, _ = gen.generate_blueprints([story], [], segments, annotations)
    for bp in blueprints:
        assert bp.blueprint_signature != ""
        assert bp.story_id == "story_001"


def test_duplicate_guard_exact():
    embedder = EmbeddingService()
    guard = DuplicateGuard(embedder)
    bp1 = StoryBlueprint(
        blueprint_id="bp1", story_id="s1", story_name="Test", validated_story_summary="test",
        segment_ids=["s1", "s2", "s3"], start_time=0, end_time=10, target_duration=10,
        story_arc={}, blueprint_signature="s1:abc123",
    )
    bp2 = StoryBlueprint(
        blueprint_id="bp2", story_id="s1", story_name="Test", validated_story_summary="test",
        segment_ids=["s1", "s2", "s3"], start_time=0, end_time=10, target_duration=10,
        story_arc={}, blueprint_signature="s1:abc123",
    )
    is_dup, reason, detail = guard.is_duplicate(bp1)
    assert is_dup is False
    is_dup, reason, detail = guard.is_duplicate(bp2)
    assert is_dup is True
    assert reason == "exact_duplicate"


def test_duplicate_guard_different_segments():
    embedder = EmbeddingService()
    guard = DuplicateGuard(embedder)
    bp1 = StoryBlueprint(
        blueprint_id="bp1", story_id="s1", story_name="Deep Work Productivity", validated_story_summary="Deep work is the key to productivity and focus",
        segment_ids=["s1", "s2", "s3"], start_time=0, end_time=10, target_duration=10,
        story_arc={},
    )
    bp2 = StoryBlueprint(
        blueprint_id="bp2", story_id="s1", story_name="Fight Distractions Now", validated_story_summary="Eliminate all distractions to improve your workflow",
        segment_ids=["s4", "s5", "s6"], start_time=10, end_time=20, target_duration=10,
        story_arc={},
    )
    guard.is_duplicate(bp1)
    is_dup, reason, _ = guard.is_duplicate(bp2)
    assert is_dup is False
