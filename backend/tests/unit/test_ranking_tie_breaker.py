from backend.ranking.tie_breaker import break_ties
from backend.ranking.models import RankedClip, Candidate


def _make_ranked(final_score, confidence=0.8, hook_quality=0.7, duration=30, hook_start=0):
    c = Candidate(id="t", hook_text="a", body_text="b", ending_text="c", hook_start=hook_start, hook_end=5, body_start=6, body_end=20, ending_start=21, ending_end=hook_start + duration, duration=duration, raw_score=final_score, flow_score=0.8)
    return RankedClip(candidate=c, final_score=final_score, overall_confidence=confidence, stage_scores={"hook_quality": hook_quality})


def test_no_ties_preserves_order():
    a = _make_ranked(0.9, 0.9, 0.8, 30)
    b = _make_ranked(0.8, 0.85, 0.7, 25)
    result = break_ties([a, b])
    assert result[0].final_score == 0.9
    assert result[1].final_score == 0.8


def test_tie_confidence_breaks():
    a = _make_ranked(0.8, confidence=0.75)
    b = _make_ranked(0.8, confidence=0.85)
    result = break_ties([a, b])
    assert result[0].overall_confidence >= result[1].overall_confidence


def test_tie_hook_quality_breaks():
    a = _make_ranked(0.8, confidence=0.8, hook_quality=0.6)
    b = _make_ranked(0.8, confidence=0.8, hook_quality=0.9)
    result = break_ties([a, b])
    assert result[0].stage_scores["hook_quality"] >= result[1].stage_scores["hook_quality"]


def test_tie_duration_breaks():
    a = _make_ranked(0.8, confidence=0.8, hook_quality=0.8, duration=40)
    b = _make_ranked(0.8, confidence=0.8, hook_quality=0.8, duration=25)
    result = break_ties([a, b])
    assert result[0].candidate.duration <= result[1].candidate.duration


def test_tie_position_breaks():
    a = _make_ranked(0.8, confidence=0.8, hook_quality=0.8, duration=30, hook_start=50)
    b = _make_ranked(0.8, confidence=0.8, hook_quality=0.8, duration=30, hook_start=10)
    result = break_ties([a, b])
    assert result[0].candidate.hook_start <= result[1].candidate.hook_start


def test_empty_list():
    assert break_ties([]) == []


def test_single_item():
    r = _make_ranked(0.8)
    result = break_ties([r])
    assert len(result) == 1
    assert result[0].final_score == 0.8
