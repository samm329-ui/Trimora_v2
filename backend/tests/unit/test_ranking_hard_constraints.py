from backend.ranking.hard_constraints import stage_hard_constraints
from backend.ranking.models import Candidate
from backend.config.ranking_config import MIN_DURATION_SECONDS, MAX_DURATION_SECONDS, MAX_GAP_SECONDS, MIN_RAW_SCORE


def test_passes_valid_candidate():
    c = Candidate(id="v", hook_text="a", body_text="b", ending_text="c", hook_start=0, hook_end=5, body_start=6, body_end=30, ending_start=31, ending_end=40, duration=40, raw_score=0.8, flow_score=0.9)
    result = stage_hard_constraints([c])
    assert len(result) == 1
    assert result[0].eliminated_at is None


def test_eliminates_duration_too_short():
    c = Candidate(id="s", hook_text="a", body_text="b", ending_text="c", hook_start=0, hook_end=2, body_start=3, body_end=8, ending_start=9, ending_end=12, duration=12, raw_score=0.8, flow_score=0.9)
    result = stage_hard_constraints([c])
    assert len(result) == 0
    assert c.eliminated_at == "hard_constraints"
    assert "duration_too_short" in c.elimination_reasons


def test_eliminates_duration_too_long():
    c = Candidate(id="l", hook_text="a", body_text="b", ending_text="c", hook_start=0, hook_end=5, body_start=6, body_end=50, ending_start=51, ending_end=100, duration=100, raw_score=0.8, flow_score=0.9)
    result = stage_hard_constraints([c])
    assert len(result) == 0
    assert "duration_too_long" in c.elimination_reasons


def test_eliminates_non_chronological():
    c = Candidate(id="nc", hook_text="a", body_text="b", ending_text="c", hook_start=10, hook_end=15, body_start=5, body_end=20, ending_start=25, ending_end=30, duration=30, raw_score=0.8, flow_score=0.9)
    result = stage_hard_constraints([c])
    assert len(result) == 0
    assert "non_chronological" in c.elimination_reasons


def test_eliminates_segment_overlap():
    c = Candidate(id="ov", hook_text="a", body_text="b", ending_text="c", hook_start=0, hook_end=10, body_start=8, body_end=20, ending_start=21, ending_end=30, duration=30, raw_score=0.8, flow_score=0.9)
    result = stage_hard_constraints([c])
    assert len(result) == 0
    assert "segment_overlap" in c.elimination_reasons


def test_eliminates_excessive_gap():
    c = Candidate(id="eg", hook_text="a", body_text="b", ending_text="c", hook_start=0, hook_end=5, body_start=40, body_end=60, ending_start=61, ending_end=70, duration=70, raw_score=0.8, flow_score=0.9)
    result = stage_hard_constraints([c])
    assert len(result) == 0
    assert "excessive_gap" in c.elimination_reasons


def test_eliminates_score_too_low():
    c = Candidate(id="sl", hook_text="a", body_text="b", ending_text="c", hook_start=0, hook_end=5, body_start=6, body_end=30, ending_start=31, ending_end=40, duration=40, raw_score=0.05, flow_score=0.9)
    result = stage_hard_constraints([c])
    assert len(result) == 0
    assert "score_too_low" in c.elimination_reasons


def test_boundary_duration_min():
    c = Candidate(id="bd", hook_text="a", body_text="b", ending_text="c", hook_start=0, hook_end=5, body_start=6, body_end=10, ending_start=11, ending_end=15, duration=15, raw_score=0.8, flow_score=0.9)
    result = stage_hard_constraints([c])
    assert len(result) == 1


def test_boundary_duration_max():
    c = Candidate(id="bdx", hook_text="a", body_text="b", ending_text="c", hook_start=0, hook_end=5, body_start=6, body_end=50, ending_start=51, ending_end=90, duration=90, raw_score=0.8, flow_score=0.9)
    result = stage_hard_constraints([c])
    assert len(result) == 1


def test_eliminates_multiple_reasons():
    c = Candidate(id="mr", hook_text="a", body_text="b", ending_text="c", hook_start=10, hook_end=15, body_start=5, body_end=50, ending_start=51, ending_end=100, duration=100, raw_score=0.05, flow_score=0.9)
    result = stage_hard_constraints([c])
    assert len(result) == 0
    assert len(c.elimination_reasons) >= 2
