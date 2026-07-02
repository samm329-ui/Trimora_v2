import pytest
from backend.services.scoring_service import ScoringService
from backend.tests.fixtures.sample_video import make_segments, make_features


def test_generate_candidates_returns_candidates():
    segments = make_segments()
    features = make_features()
    svc = ScoringService()
    candidates = svc.generate_candidates(segments, features, top_k=20, min_score=0.2)
    assert len(candidates) > 0
    for c in candidates:
        assert c.id.startswith("clip_")
        assert c.duration > 0
        assert 0.0 <= c.total_score <= 1.0


def test_candidates_have_text():
    segments = make_segments()
    features = make_features()
    svc = ScoringService()
    candidates = svc.generate_candidates(segments, features, top_k=5, min_score=0.2)
    for c in candidates:
        assert c.hook_text != ""
        assert c.body_text != ""
        assert c.ending_text != ""


def test_candidates_have_chronological_order():
    segments = make_segments()
    features = make_features()
    svc = ScoringService()
    candidates = svc.generate_candidates(segments, features, top_k=50, min_score=0.0)
    for c in candidates:
        assert c.hook_start <= c.body_start <= c.ending_start


def test_candidates_no_overlap():
    segments = make_segments()
    features = make_features()
    svc = ScoringService()
    candidates = svc.generate_candidates(segments, features, top_k=50, min_score=0.0)
    for c in candidates:
        assert c.hook_end <= c.body_start
        assert c.body_end <= c.ending_start


def test_candidates_respect_top_k():
    segments = make_segments()
    features = make_features()
    svc = ScoringService()
    candidates = svc.generate_candidates(segments, features, top_k=3, min_score=0.0)
    assert len(candidates) <= 3


def test_candidates_sorted_by_score():
    segments = make_segments()
    features = make_features()
    svc = ScoringService()
    candidates = svc.generate_candidates(segments, features, top_k=20, min_score=0.0)
    for i in range(len(candidates) - 1):
        assert candidates[i].total_score >= candidates[i + 1].total_score


def test_flow_score():
    from backend.models.segment import AtomicSegment
    svc = ScoringService()
    hook = AtomicSegment(id="h", start=0.0, end=5.0, text="Hook", kind="hook", order=0)
    body = AtomicSegment(id="b", start=6.0, end=20.0, text="Body", kind="body", order=1)
    ending = AtomicSegment(id="e", start=21.0, end=25.0, text="Ending", kind="ending", order=2)
    flow = svc._flow_score(hook, body, ending)
    assert 0.1 <= flow <= 0.95


def test_flow_score_penalizes_large_gaps():
    svc = ScoringService()
    from backend.models.segment import AtomicSegment
    hook = AtomicSegment(id="h", start=0.0, end=5.0, text="Hook", kind="hook", order=0)
    body = AtomicSegment(id="b", start=200.0, end=220.0, text="Body", kind="body", order=1)
    ending = AtomicSegment(id="e", start=300.0, end=305.0, text="Ending", kind="ending", order=2)
    flow = svc._flow_score(hook, body, ending)
    assert flow < 0.5


def test_generate_candidates_empty_segments():
    svc = ScoringService()
    candidates = svc.generate_candidates([], [], top_k=5, min_score=0.1)
    assert candidates == []


def test_apply_duration_penalty():
    svc = ScoringService()
    score = 0.8
    assert svc._apply_duration_penalty(score, 10) == pytest.approx(0.4)
    assert svc._apply_duration_penalty(score, 20) == pytest.approx(0.64)
    assert svc._apply_duration_penalty(score, 45) == pytest.approx(0.8)
    assert svc._apply_duration_penalty(score, 80) == pytest.approx(0.72)
    assert svc._apply_duration_penalty(score, 120) == pytest.approx(0.56)
