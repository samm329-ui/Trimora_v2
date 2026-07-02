from backend.services.segmentation_service import SegmentationService, HOOK_PATTERNS, ENDING_PATTERNS
from backend.models.transcript import TranscriptChunk


def test_build_atomic_segments_creates_segments():
    chunks = [TranscriptChunk(chunk_id="chunk_0", start=0.0, end=10.0, text="What if this changes everything? Here is the content. So that is why.", confidence=0.9)]
    svc = SegmentationService()
    segments = svc.build_atomic_segments(chunks)
    assert len(segments) >= 3


def test_hook_detection_first_sentence():
    from backend.models.transcript import TranscriptChunk
    chunks = [TranscriptChunk(chunk_id="chunk_0", start=0.0, end=5.0, text="What if this changes everything?", confidence=0.9)]
    svc = SegmentationService()
    segments = svc.build_atomic_segments(chunks)
    assert segments[0].kind == "hook"


def test_ending_detection_last_sentence():
    chunks = [TranscriptChunk(chunk_id="chunk_0", start=0.0, end=10.0, text="Here is some content. So that is why deep work matters. Subscribe for more.", confidence=0.9)]
    svc = SegmentationService()
    segments = svc.build_atomic_segments(chunks)
    assert segments[-1].kind == "ending"


def test_body_classification():
    chunks = [TranscriptChunk(chunk_id="chunk_0", start=0.0, end=10.0, text="This is just a regular sentence with no hook or ending patterns.", confidence=0.9)]
    svc = SegmentationService()
    segments = svc.build_atomic_segments(chunks)
    for s in segments:
        assert s.kind == "body"


def test_merge_small_segments():
    from backend.models.segment import AtomicSegment
    svc = SegmentationService()
    segments = [
        AtomicSegment(id="a", start=0.0, end=0.5, text="Hi", kind="hook", order=0),
        AtomicSegment(id="b", start=0.5, end=5.0, text="This is a longer sentence.", kind="body", order=1),
    ]
    merged = svc._merge_small_segments(segments, min_duration=1.0)
    assert len(merged) < len(segments)


def test_hook_patterns_match():
    import re
    for pattern in HOOK_PATTERNS:
        assert isinstance(pattern, re.Pattern)


def test_ending_patterns_match():
    import re
    for pattern in ENDING_PATTERNS:
        assert isinstance(pattern, re.Pattern)


def test_empty_chunks():
    svc = SegmentationService()
    segments = svc.build_atomic_segments([])
    assert segments == []


def test_chunk_with_only_punctuation():
    chunks = [TranscriptChunk(chunk_id="c", start=0.0, end=1.0, text="...", confidence=0.5)]
    svc = SegmentationService()
    segments = svc.build_atomic_segments(chunks)
    assert len(segments) >= 1
