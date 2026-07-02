from backend.ranking import RankingEngine, Candidate
from backend.services.embedding_service import EmbeddingService
from backend.services.scoring_service import ScoringService
from backend.services.segmentation_service import SegmentationService
from backend.services.feature_service import FeatureService
from backend.services.audio_service import AudioService
from backend.tests.fixtures.sample_video import make_transcript_chunks, make_segments, make_features
from backend.utils.text_utils import split_sentences


def test_segmentation_to_features_integration():
    chunks = make_transcript_chunks()
    seg_svc = SegmentationService()
    feat_svc = FeatureService()

    segments = seg_svc.build_atomic_segments(chunks)
    assert len(segments) > 0

    features = [feat_svc.compute_features(s) for s in segments]
    assert len(features) == len(segments)

    for f in features:
        assert 0.0 <= f.total_score <= 1.0
        assert f.segment_id != ""


def test_features_to_candidates_integration():
    segments = make_segments()
    features = make_features()
    svc = ScoringService()
    candidates = svc.generate_candidates(segments, features, top_k=20, min_score=0.2)
    assert len(candidates) > 0
    for c in candidates:
        assert c.hook_text != ""
        assert c.body_text != ""
        assert c.ending_text != ""
        assert c.hook_start <= c.body_start <= c.ending_start


def test_candidates_to_ranking_integration():
    segments = make_segments()
    features = make_features()
    scoring_svc = ScoringService()
    ranking_engine = RankingEngine(embedder=EmbeddingService())

    candidates = scoring_svc.generate_candidates(segments, features, top_k=50, min_score=0.0)
    assert len(candidates) > 0

    ranking_candidates = [
        Candidate(
            id=c.id, hook_text=c.hook_text, body_text=c.body_text, ending_text=c.ending_text,
            hook_start=c.hook_start, hook_end=c.hook_end, body_start=c.body_start, body_end=c.body_end,
            ending_start=c.ending_start, ending_end=c.ending_end,
            duration=c.duration, raw_score=c.total_score, flow_score=c.flow_score,
        )
        for c in candidates
    ]

    result = ranking_engine.rank(ranking_candidates, job_id="integration_test")
    assert result.total_candidates == len(ranking_candidates)
    assert len(result.ranked_clips) > 0
    assert result.ranked_clips[0].rank == 1

    for rc in result.ranked_clips:
        assert rc.final_score > 0
        assert rc.explanation != ""


def test_full_ranking_pipeline_deterministic():
    segments = make_segments()
    features = make_features()
    scoring_svc = ScoringService()
    engine = RankingEngine(embedder=EmbeddingService())

    ranking_candidates = [
        Candidate(
            id=c.id, hook_text=c.hook_text, body_text=c.body_text, ending_text=c.ending_text,
            hook_start=c.hook_start, hook_end=c.hook_end, body_start=c.body_start, body_end=c.body_end,
            ending_start=c.ending_start, ending_end=c.ending_end,
            duration=c.duration, raw_score=c.total_score, flow_score=c.flow_score,
        )
        for c in scoring_svc.generate_candidates(segments, features, top_k=50, min_score=0.0)
    ]

    result1 = engine.rank(ranking_candidates, job_id="det_test")
    result2 = engine.rank(ranking_candidates, job_id="det_test")
    for r1, r2 in zip(result1.ranked_clips, result2.ranked_clips):
        assert r1.final_score == r2.final_score
        assert r1.rank == r2.rank


def test_hook_ending_patterns_in_segmentation():
    chunks = make_transcript_chunks()
    svc = SegmentationService()
    segments = svc.build_atomic_segments(chunks)

    hook_found = any(s.kind == "hook" for s in segments)
    ending_found = any(s.kind == "ending" for s in segments)
    assert hook_found, "No hook segments detected"
    assert ending_found, "No ending segments detected"


def test_overlap_removal():
    chunks = make_transcript_chunks()
    merged_sentences = []
    seen = set()
    for chunk in chunks:
        for sentence in split_sentences(chunk.text):
            normalized = sentence.strip().lower()
            if normalized not in seen:
                seen.add(normalized)
                merged_sentences.append(sentence)
    merged_text = " ".join(merged_sentences)

    all_raw = " ".join(c.text for c in chunks)
    assert len(merged_text) <= len(all_raw), "Overlap removal should reduce or equal text length"
    assert len(merged_sentences) > 0, "Should have sentences after merge"
