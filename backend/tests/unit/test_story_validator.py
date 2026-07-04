import pytest
from backend.services.story_validator import StoryValidator
from backend.models.semantic import SegmentAnnotations, SegmentAnnotation
from backend.models.story import Story
from backend.tests.fixtures.sample_video import make_segments


def _make_annotations():
    annotations = [
        SegmentAnnotation(segment_id="seg_h_0", topic="productivity", story_role="hook", hook_strength=0.9, importance_score=0.8, emotion="curiosity", keywords=["what", "if"]),
        SegmentAnnotation(segment_id="seg_b_0", topic="productivity", story_role="body", importance_score=0.7, emotion="neutral", keywords=["truth", "waste"]),
        SegmentAnnotation(segment_id="seg_b_1", topic="deep work", story_role="body", importance_score=0.85, emotion="determination", keywords=["key", "focus"]),
        SegmentAnnotation(segment_id="seg_b_2", topic="deep work", story_role="body", importance_score=0.75, emotion="calm", keywords=["block", "hours"]),
        SegmentAnnotation(segment_id="seg_e_0", topic="deep work", story_role="ending", ending_strength=0.8, importance_score=0.7, emotion="satisfaction", keywords=["matters"]),
        SegmentAnnotation(segment_id="seg_e_1", topic="productivity", story_role="ending", ending_strength=0.6, importance_score=0.5, emotion="neutral", keywords=["subscribe"]),
    ]
    return SegmentAnnotations(job_id="job_1", annotations=annotations, relationships=[])


def _make_stories():
    return [
        Story(
            story_id="story_001",
            story_name="Deep Work",
            segment_ids=["seg_h_0", "seg_b_0", "seg_b_1", "seg_b_2", "seg_e_0"],
            llm_story_summary="Deep work matters for productivity",
        ),
    ]


def test_validate_stories():
    segments = make_segments()
    annotations = _make_annotations()
    stories = _make_stories()
    validator = StoryValidator()
    validated, rejected = validator.validate_stories(stories, [], segments, annotations)
    assert len(validated) >= 1
    for s in validated:
        assert s.validated is True
        assert s.story_quality_score > 0


def test_validate_stories_generates_summary():
    segments = make_segments()
    annotations = _make_annotations()
    stories = _make_stories()
    validator = StoryValidator()
    validated, _ = validator.validate_stories(stories, [], segments, annotations)
    for s in validated:
        assert s.validated_story_summary != ""


def test_validate_stories_priority():
    segments = make_segments()
    annotations = _make_annotations()
    stories = _make_stories()
    validator = StoryValidator()
    validated, _ = validator.validate_stories(stories, [], segments, annotations)
    for i, s in enumerate(validated):
        assert s.story_priority == i + 1


def test_validate_stories_rejects_low_quality():
    segments = make_segments()
    annotations = SegmentAnnotations(job_id="job_1", annotations=[], relationships=[])
    story = Story(story_id="story_002", story_name="Bad", segment_ids=["seg_h_0"])
    validator = StoryValidator()
    validated, rejected = validator.validate_stories([story], [], segments, annotations)
    assert len(validated) == 0
    assert len(rejected) == 1
    assert rejected[0].rejection_reason != ""


def test_validate_stories_empty():
    segments = make_segments()
    annotations = _make_annotations()
    validator = StoryValidator()
    validated, rejected = validator.validate_stories([], [], segments, annotations)
    assert len(validated) == 0
    assert len(rejected) == 0
