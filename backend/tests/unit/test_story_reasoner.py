import json
import pytest
from pathlib import Path
from backend.services.llm_provider import LLMProvider
from backend.services.story_reasoner import StoryReasoner, Pass2Error
from backend.models.semantic import SegmentAnnotations, SegmentAnnotation, LLMStoryBoundary
from backend.models.topic_block import TopicBlock
from backend.tests.fixtures.sample_video import make_segments


class MockLLMProvider(LLMProvider):
    def complete(self, prompt, response_format="json"):
        return {
            "stories": [
                {
                    "boundary_segments": ["seg_h_0", "seg_b_0", "seg_b_1", "seg_b_2", "seg_e_0"],
                    "story_summary": "Deep work is the key to productivity. Focus on important tasks and eliminate distractions.",
                    "suggested_name": "Deep Work Matters",
                    "start_confidence": 0.85,
                    "end_confidence": 0.75,
                    "boundary_confidence": 0.8,
                    "ambiguous_segments": [],
                },
                {
                    "boundary_segments": ["seg_b_3", "seg_b_4", "seg_e_1"],
                    "story_summary": "Distractions kill productivity. Turn off notifications and focus.",
                    "suggested_name": "Fight Distractions",
                    "start_confidence": 0.7,
                    "end_confidence": 0.65,
                    "boundary_confidence": 0.68,
                    "ambiguous_segments": ["seg_b_3"],
                },
            ]
        }


def _make_annotations():
    annotations = []
    for sid in ["seg_h_0", "seg_b_0", "seg_b_1", "seg_b_2", "seg_b_3", "seg_b_4", "seg_e_0", "seg_e_1"]:
        annotations.append(SegmentAnnotation(segment_id=sid, topic="productivity", story_role="body"))
    return SegmentAnnotations(job_id="job_1", annotations=annotations, relationships=[])


def _make_blocks() -> list[TopicBlock]:
    segments = make_segments()
    return [
        TopicBlock(
            segments=segments,
            start=0.0,
            end=39.0,
            original_block_index=0,
            structural_confidence=0.9,
            synopsis="Deep work vs distractions",
            representative_excerpt="What if I told you everything you know about productivity is wrong?",
        ),
    ]


def test_detect_story_boundaries_returns_boundaries():
    segments = make_segments()
    annotations = _make_annotations()
    blocks = _make_blocks()
    provider = MockLLMProvider()
    reasoner = StoryReasoner(provider)
    boundaries, raw = reasoner.detect_story_boundaries(segments, annotations, blocks=blocks)
    assert len(boundaries) == 2
    assert all(isinstance(b, LLMStoryBoundary) for b in boundaries)
    assert boundaries[0].suggested_name == "Deep Work Matters"
    assert boundaries[1].suggested_name == "Fight Distractions"


def test_detect_story_boundaries_with_summary():
    segments = make_segments()
    annotations = _make_annotations()
    blocks = _make_blocks()
    provider = MockLLMProvider()
    reasoner = StoryReasoner(provider)
    boundaries, _ = reasoner.detect_story_boundaries(
        segments, annotations, blocks=blocks,
        summary="A productivity video about deep work and avoiding distractions.",
    )
    assert len(boundaries) == 2
    for b in boundaries:
        assert 0.0 <= b.start_confidence <= 1.0
        assert 0.0 <= b.end_confidence <= 1.0
        assert 0.0 <= b.boundary_confidence <= 1.0


def test_detect_story_boundaries_confidence():
    segments = make_segments()
    annotations = _make_annotations()
    blocks = _make_blocks()
    provider = MockLLMProvider()
    reasoner = StoryReasoner(provider)
    boundaries, _ = reasoner.detect_story_boundaries(segments, annotations, blocks=blocks)
    for b in boundaries:
        assert 0.0 <= b.start_confidence <= 1.0
        assert 0.0 <= b.end_confidence <= 1.0
        assert 0.0 <= b.boundary_confidence <= 1.0
        assert 0.0 <= b.structural_confidence <= 1.0
        assert 0.0 <= b.semantic_confidence <= 1.0


def test_detect_story_boundaries_empty():
    provider = MockLLMProvider()
    reasoner = StoryReasoner(provider)
    annotations = SegmentAnnotations(job_id="job_1", annotations=[], relationships=[])
    boundaries, raw = reasoner.detect_story_boundaries([], annotations, blocks=[])
    assert len(boundaries) == 0


def test_pass2_checkpoint_save_and_load(tmp_path):
    segments = make_segments()
    annotations = _make_annotations()
    blocks = _make_blocks()
    provider = MockLLMProvider()
    reasoner = StoryReasoner(provider)
    checkpoint_path = tmp_path / "pass2_checkpoint.jsonl"

    boundaries1, _ = reasoner.detect_story_boundaries(
        segments, annotations, blocks=blocks, checkpoint_path=checkpoint_path,
    )
    assert checkpoint_path.exists()

    with open(checkpoint_path, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) >= 1
    entry = json.loads(lines[0])
    assert "block_index" in entry
    assert "boundaries" in entry
    assert "raw" in entry


def test_pass2_resume_from_checkpoint(tmp_path):
    segments = make_segments()
    annotations = _make_annotations()
    blocks = _make_blocks()
    provider = MockLLMProvider()
    reasoner = StoryReasoner(provider)
    checkpoint_path = tmp_path / "pass2_checkpoint.jsonl"

    boundaries1, _ = reasoner.detect_story_boundaries(
        segments, annotations, blocks=blocks, checkpoint_path=checkpoint_path,
    )

    boundaries2, _ = reasoner.detect_story_boundaries(
        segments, annotations, blocks=blocks, checkpoint_path=checkpoint_path,
    )

    assert len(boundaries2) == len(boundaries1)


def test_pass2_progress_callback(tmp_path):
    segments = make_segments()
    annotations = _make_annotations()
    blocks = _make_blocks()
    provider = MockLLMProvider()
    reasoner = StoryReasoner(provider)
    progress_log = []

    def callback(block_idx, total_blocks):
        progress_log.append((block_idx, total_blocks))

    reasoner.detect_story_boundaries(
        segments, annotations, blocks=blocks, progress_callback=callback,
    )

    assert len(progress_log) >= 1


def test_pass2_boundary_segments_are_valid():
    segments = make_segments()
    annotations = _make_annotations()
    blocks = _make_blocks()
    provider = MockLLMProvider()
    reasoner = StoryReasoner(provider)
    boundaries, _ = reasoner.detect_story_boundaries(segments, annotations, blocks=blocks)

    all_seg_ids = {s.id for s in segments}
    for b in boundaries:
        for seg_id in b.boundary_segments:
            assert seg_id in all_seg_ids, f"Segment {seg_id} not in valid segment IDs"
