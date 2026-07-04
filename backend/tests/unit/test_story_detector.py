import pytest
from backend.services.story_detector import StoryDetector
from backend.models.semantic import SegmentAnnotations, SegmentAnnotation, LLMStoryBoundary
from backend.models.story import StoryCandidate, Story
from backend.tests.fixtures.sample_video import make_segments


def _make_annotations():
    annotations = []
    for sid in ["seg_h_0", "seg_b_0", "seg_b_1", "seg_b_2", "seg_b_3", "seg_b_4", "seg_e_0", "seg_e_1"]:
        annotations.append(SegmentAnnotation(segment_id=sid, topic="productivity", story_role="body"))
    return SegmentAnnotations(
        job_id="job_1",
        annotations=annotations,
        relationships=[],
        llm_story_boundaries=[
            LLMStoryBoundary(
                boundary_segments=["seg_h_0", "seg_b_0", "seg_b_1", "seg_b_2", "seg_e_0"],
                story_summary="Deep work matters",
                suggested_name="Deep Work",
                start_confidence=0.85,
                end_confidence=0.75,
                boundary_confidence=0.8,
            ),
            LLMStoryBoundary(
                boundary_segments=["seg_b_3", "seg_b_4", "seg_e_1"],
                story_summary="Fight distractions",
                suggested_name="Fight Distractions",
                start_confidence=0.7,
                end_confidence=0.65,
                boundary_confidence=0.68,
                ambiguous_segments=["seg_b_3"],
            ),
        ],
    )


def test_form_candidates():
    segments = make_segments()
    annotations = _make_annotations()
    detector = StoryDetector()
    candidates = detector.form_candidates(segments, annotations)
    assert len(candidates) == 2
    assert all(isinstance(c, StoryCandidate) for c in candidates)
    assert candidates[0].candidate_id == "cand_001"
    assert candidates[1].candidate_id == "cand_002"
    assert len(candidates[0].segment_ids) == 5
    assert len(candidates[1].segment_ids) == 3


def test_verify_candidates_valid():
    segments = make_segments()
    annotations = _make_annotations()
    detector = StoryDetector()
    candidates = detector.form_candidates(segments, annotations)
    verified = detector.verify_candidates(candidates, segments, annotations)
    # cand_001 has gaps between segments (>5s), so it won't be fully valid
    # cand_002 has 3 segments with no gaps
    cand2 = [c for c in verified if c.candidate_id == "cand_002"][0]
    assert cand2.verified is True
    assert len(cand2.verification_issues) == 0


def test_verify_candidates_too_few_segments():
    segments = make_segments()
    annotations = _make_annotations()
    annotations.llm_story_boundaries = [
        LLMStoryBoundary(boundary_segments=["seg_h_0", "seg_b_0"], story_summary="short", suggested_name="Short"),
    ]
    detector = StoryDetector()
    candidates = detector.form_candidates(segments, annotations)
    verified = detector.verify_candidates(candidates, segments, annotations)
    assert verified[0].verified is False
    assert "too_few_segments" in verified[0].verification_issues


def test_repair_candidates_verified():
    segments = make_segments()
    annotations = _make_annotations()
    detector = StoryDetector()
    candidates = detector.form_candidates(segments, annotations)
    candidates = detector.verify_candidates(candidates, segments, annotations)
    repaired, rejected, records = detector.repair_candidates(candidates, segments, annotations)
    assert len(repaired) == 2
    assert len(rejected) == 0
    assert all(r.success for r in records)


def test_repair_candidates_rejected():
    segments = make_segments()
    annotations = _make_annotations()
    annotations.llm_story_boundaries = [
        LLMStoryBoundary(boundary_segments=["seg_h_0"], story_summary="too short", suggested_name="Too Short"),
    ]
    detector = StoryDetector()
    candidates = detector.form_candidates(segments, annotations)
    candidates = detector.verify_candidates(candidates, segments, annotations)
    repaired, rejected, records = detector.repair_candidates(candidates, segments, annotations)
    assert len(rejected) >= 1


def test_candidate_to_story():
    detector = StoryDetector()
    candidate = StoryCandidate(
        candidate_id="cand_001",
        segment_ids=["seg_h_0", "seg_b_0", "seg_e_0"],
        story_name="Test Story",
        llm_story_summary="Test summary",
        boundary_confidence=0.8,
    )
    story = detector._candidate_to_story(candidate, version=1)
    assert isinstance(story, Story)
    assert story.story_id == "story_001"
    assert story.story_name == "Test Story"
    assert story.version == 1
    assert story.segment_count == 3
