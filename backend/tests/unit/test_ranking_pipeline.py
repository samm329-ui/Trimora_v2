from backend.ranking import RankingEngine, Candidate
from backend.services.embedding_service import EmbeddingService
from backend.tests.fixtures.sample_video import make_ranking_candidates


def test_ranking_engine_runs():
    embedder = EmbeddingService()
    engine = RankingEngine(embedder=embedder)
    candidates = make_ranking_candidates()
    result = engine.rank(candidates, job_id="test_job")
    assert result.job_id == "test_job"
    assert result.total_candidates == len(candidates)
    assert result.after_hard_constraints <= result.total_candidates
    assert len(result.ranked_clips) > 0
    assert result.ranking_config is not None


def test_ranking_eliminates_invalid():
    embedder = EmbeddingService()
    engine = RankingEngine(embedder=embedder)
    candidates = make_ranking_candidates()
    candidates.append(
        Candidate(id="invalid", hook_text="a", body_text="b", ending_text="c", hook_start=0, hook_end=2, body_start=3, body_end=8, ending_start=9, ending_end=12, duration=12, raw_score=0.1, flow_score=0.5)
    )
    result = engine.rank(candidates, job_id="test_job")
    assert result.after_hard_constraints < result.total_candidates
    assert any("duration_too_short" in e["reasons"] for e in result.eliminated_clips)


def test_ranking_deterministic():
    embedder = EmbeddingService()
    engine = RankingEngine(embedder=embedder)
    candidates = make_ranking_candidates()
    result1 = engine.rank(candidates, job_id="test")
    result2 = engine.rank(candidates, job_id="test")
    for r1, r2 in zip(result1.ranked_clips, result2.ranked_clips):
        assert r1.final_score == r2.final_score
        assert r1.rank == r2.rank


def test_ranking_empty_input():
    embedder = EmbeddingService()
    engine = RankingEngine(embedder=embedder)
    result = engine.rank([], job_id="empty")
    assert result.total_candidates == 0
    assert len(result.ranked_clips) == 0


def test_ranking_single_candidate():
    embedder = EmbeddingService()
    engine = RankingEngine(embedder=embedder)
    c = Candidate(id="only", hook_text="How to code", body_text="Practice daily", ending_text="Subscribe", hook_start=0, hook_end=3, body_start=4, body_end=20, ending_start=21, ending_end=25, duration=25, raw_score=0.8, flow_score=0.85)
    result = engine.rank([c], job_id="single")
    assert len(result.ranked_clips) == 1
    assert result.ranked_clips[0].rank == 1
    assert result.ranked_clips[0].explanation != ""


def test_ranking_includes_explanations():
    embedder = EmbeddingService()
    engine = RankingEngine(embedder=embedder)
    candidates = make_ranking_candidates()
    result = engine.rank(candidates, job_id="explain")
    for rc in result.ranked_clips:
        assert rc.explanation != ""
        assert "Rank #" in rc.explanation


def test_ranking_includes_eliminated():
    embedder = EmbeddingService()
    engine = RankingEngine(embedder=embedder)
    candidates = make_ranking_candidates()
    candidates.append(
        Candidate(id="elim", hook_text="a", body_text="b", ending_text="c", hook_start=100, hook_end=105, body_start=50, body_end=80, ending_start=81, ending_end=90, duration=90, raw_score=0.8, flow_score=0.9)
    )
    result = engine.rank(candidates, job_id="elim_test")
    assert len(result.eliminated_clips) > 0
