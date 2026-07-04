import json
import pytest
from pathlib import Path
from backend.services.llm_provider import LLMProvider
from backend.services.semantic_service import SemanticService, SemanticEnrichmentError
from backend.models.semantic import SegmentAnnotations
from backend.models.topic_block import TopicBlock
from backend.tests.fixtures.sample_video import make_segments


class MockLLMProvider(LLMProvider):
    def complete(self, prompt, response_format="json"):
        segments = [
            {"segment_id": "seg_h_0", "topic": "productivity", "subtopic": "deep work", "story_role": "hook", "intent": "question", "emotion": "curiosity", "emotion_intensity": 0.8, "importance_score": 0.9, "hook_strength": 0.95, "ending_strength": 0.0, "curiosity_score": 0.9, "information_density": 0.7, "standalone_score": 0.8, "completeness_score": 0.7, "context_dependency": "low", "key_entities": ["productivity"], "keywords": ["what", "if", "told"], "confidence_score": 0.85},
            {"segment_id": "seg_b_0", "topic": "productivity", "subtopic": "wasted time", "story_role": "body", "intent": "explain", "emotion": "neutral", "emotion_intensity": 0.4, "importance_score": 0.7, "hook_strength": 0.0, "ending_strength": 0.0, "curiosity_score": 0.3, "information_density": 0.8, "standalone_score": 0.6, "completeness_score": 0.8, "context_dependency": "medium", "key_entities": ["tasks"], "keywords": ["truth", "waste", "hours"], "confidence_score": 0.8},
            {"segment_id": "seg_b_1", "topic": "deep work", "subtopic": "focus", "story_role": "body", "intent": "explain", "emotion": "determination", "emotion_intensity": 0.6, "importance_score": 0.85, "hook_strength": 0.0, "ending_strength": 0.0, "curiosity_score": 0.4, "information_density": 0.9, "standalone_score": 0.7, "completeness_score": 0.9, "context_dependency": "low", "key_entities": ["deep work"], "keywords": ["key", "insight", "focus"], "confidence_score": 0.85},
            {"segment_id": "seg_b_2", "topic": "deep work", "subtopic": "scheduling", "story_role": "body", "intent": "explain", "emotion": "calm", "emotion_intensity": 0.3, "importance_score": 0.75, "hook_strength": 0.0, "ending_strength": 0.0, "curiosity_score": 0.2, "information_density": 0.85, "standalone_score": 0.65, "completeness_score": 0.85, "context_dependency": "medium", "key_entities": ["morning"], "keywords": ["block", "hours", "project"], "confidence_score": 0.8},
            {"segment_id": "seg_b_3", "topic": "distractions", "subtopic": "enemy", "story_role": "body", "intent": "argue", "emotion": "frustration", "emotion_intensity": 0.7, "importance_score": 0.8, "hook_strength": 0.0, "ending_strength": 0.0, "curiosity_score": 0.3, "information_density": 0.75, "standalone_score": 0.7, "completeness_score": 0.7, "context_dependency": "low", "key_entities": ["distractions"], "keywords": ["enemy", "progress"], "confidence_score": 0.82},
            {"segment_id": "seg_b_4", "topic": "focus", "subtopic": "elimination", "story_role": "body", "intent": "explain", "emotion": "calm", "emotion_intensity": 0.2, "importance_score": 0.65, "hook_strength": 0.0, "ending_strength": 0.0, "curiosity_score": 0.1, "information_density": 0.7, "standalone_score": 0.6, "completeness_score": 0.75, "context_dependency": "low", "key_entities": ["notifications"], "keywords": ["turn", "off", "close"], "confidence_score": 0.78},
            {"segment_id": "seg_e_0", "topic": "deep work", "subtopic": "conclusion", "story_role": "ending", "intent": "conclude", "emotion": "satisfaction", "emotion_intensity": 0.5, "importance_score": 0.7, "hook_strength": 0.0, "ending_strength": 0.8, "curiosity_score": 0.0, "information_density": 0.5, "standalone_score": 0.5, "completeness_score": 0.6, "context_dependency": "high", "key_entities": ["deep work"], "keywords": ["matters"], "confidence_score": 0.75},
            {"segment_id": "seg_e_1", "topic": "productivity", "subtopic": "cta", "story_role": "ending", "intent": "conclude", "emotion": "neutral", "emotion_intensity": 0.3, "importance_score": 0.5, "hook_strength": 0.0, "ending_strength": 0.6, "curiosity_score": 0.0, "information_density": 0.3, "standalone_score": 0.4, "completeness_score": 0.5, "context_dependency": "low", "key_entities": [], "keywords": ["subscribe", "tips"], "confidence_score": 0.7},
        ]
        return {"annotations": segments, "relationships": []}


def _make_blocks(segments) -> list[TopicBlock]:
    return [
        TopicBlock(
            segments=segments,
            start=segments[0].start,
            end=segments[-1].end,
            original_block_index=0,
            structural_confidence=0.9,
        ),
    ]


def test_annotate_segments_returns_annotations():
    segments = make_segments()
    provider = MockLLMProvider()
    svc = SemanticService(provider)
    blocks = _make_blocks(segments)
    annotations, raw = svc.annotate_segments(segments, blocks, "test transcript", "job_1")
    assert isinstance(annotations, SegmentAnnotations)
    assert annotations.job_id == "job_1"
    assert len(annotations.annotations) == 8


def test_annotate_segments_clamps_scores():
    segments = make_segments()
    provider = MockLLMProvider()
    svc = SemanticService(provider)
    blocks = _make_blocks(segments)
    annotations, _ = svc.annotate_segments(segments, blocks, "test", "job_1")
    for a in annotations.annotations:
        assert 0.0 <= a.emotion_intensity <= 1.0
        assert 0.0 <= a.importance_score <= 1.0
        assert 0.0 <= a.hook_strength <= 1.0
        assert 0.0 <= a.ending_strength <= 1.0
        assert 0.0 <= a.confidence_score <= 1.0


def test_annotate_segments_empty():
    provider = MockLLMProvider()
    svc = SemanticService(provider)
    annotations, raw = svc.annotate_segments([], [], "", "job_1")
    assert len(annotations.annotations) == 0


def test_checkpoint_save_and_load(tmp_path):
    segments = make_segments()
    provider = MockLLMProvider()
    svc = SemanticService(provider)
    blocks = _make_blocks(segments)
    checkpoint_path = tmp_path / "checkpoint.jsonl"

    annotations1, _ = svc.annotate_segments(segments, blocks, "test", "job_1", checkpoint_path=checkpoint_path)
    assert checkpoint_path.exists()

    with open(checkpoint_path, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) >= 1
    entry = json.loads(lines[0])
    assert "segment_ids" in entry
    assert "annotations" in entry
    assert "relationships" in entry
    assert "raw" in entry


def test_resume_from_checkpoint(tmp_path):
    segments = make_segments()
    provider = MockLLMProvider()
    svc = SemanticService(provider)
    blocks = _make_blocks(segments)
    checkpoint_path = tmp_path / "checkpoint.jsonl"

    annotations1, _ = svc.annotate_segments(segments, blocks, "test", "job_1", checkpoint_path=checkpoint_path)
    annotations2, _ = svc.annotate_segments(segments, blocks, "test", "job_1", checkpoint_path=checkpoint_path)

    assert len(annotations2.annotations) == len(annotations1.annotations)


def test_progress_callback(tmp_path):
    segments = make_segments()
    provider = MockLLMProvider()
    svc = SemanticService(provider)
    blocks = _make_blocks(segments)
    progress_log = []

    def callback(batch_idx, total_batches):
        progress_log.append((batch_idx, total_batches))

    annotations, _ = svc.annotate_segments(
        segments, blocks, "test", "job_1",
        progress_callback=callback,
    )

    assert len(progress_log) >= 1
    assert progress_log[-1][0] == progress_log[-1][1]


class FailingAfterFirstLLMProvider(LLMProvider):
    def __init__(self):
        self.call_count = 0

    def complete(self, prompt, response_format="json"):
        self.call_count += 1
        if self.call_count > 1:
            raise RuntimeError("LLM API timeout")
        return {
            "annotations": [
                {"segment_id": "seg_h_0", "topic": "test", "subtopic": "test", "story_role": "hook", "intent": "explain", "emotion": "neutral", "emotion_intensity": 0.5, "importance_score": 0.5, "hook_strength": 0.5, "ending_strength": 0.5, "curiosity_score": 0.5, "information_density": 0.5, "standalone_score": 0.5, "completeness_score": 0.5, "context_dependency": "low", "key_entities": [], "keywords": [], "confidence_score": 0.5}
            ],
            "relationships": [],
        }


def test_error_raises_semantic_enrichment_error(tmp_path):
    """Failed batches raise SemanticEnrichmentError with partial results and checkpoint."""
    segments = make_segments() * 4  # 32 segments
    provider = FailingAfterFirstLLMProvider()
    svc = SemanticService(provider)
    blocks = _make_blocks(segments)
    checkpoint_path = tmp_path / "checkpoint.jsonl"

    import backend.config.settings as settings_mod
    original_batch = settings_mod.settings.semantic_batch_size
    original_overlap = settings_mod.settings.semantic_context_overlap
    settings_mod.settings.semantic_batch_size = 10
    settings_mod.settings.semantic_context_overlap = 2

    try:
        with pytest.raises(SemanticEnrichmentError) as exc_info:
            svc.annotate_segments(segments, blocks, "test", "job_1", checkpoint_path=checkpoint_path)

        assert len(exc_info.value.partial_annotations) >= 1
        assert "LLM call failed" in str(exc_info.value)
        assert exc_info.value.last_batch_index >= 1

        assert checkpoint_path.exists()
    finally:
        settings_mod.settings.semantic_batch_size = original_batch
        settings_mod.settings.semantic_context_overlap = original_overlap


def test_corrupted_checkpoint_starts_fresh(tmp_path):
    segments = make_segments()
    provider = MockLLMProvider()
    svc = SemanticService(provider)
    blocks = _make_blocks(segments)
    checkpoint_path = tmp_path / "checkpoint.jsonl"

    with open(checkpoint_path, "w") as f:
        f.write("not valid json\n")

    annotations, _ = svc.annotate_segments(segments, blocks, "test", "job_1", checkpoint_path=checkpoint_path)
    assert len(annotations.annotations) > 0
