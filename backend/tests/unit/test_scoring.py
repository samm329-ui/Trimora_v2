from backend.models.segment import AtomicSegment
from backend.models.feature import SegmentFeatures
from backend.services.scoring_service import ScoringService


def test_scoring_service_returns_candidates():
    segments = [
        AtomicSegment(id="h", start=0, end=1, text="What if this idea changes everything?", kind="hook"),
        AtomicSegment(id="b", start=2, end=5, text="Here is the explanation.", kind="body"),
        AtomicSegment(id="e", start=6, end=7, text="So that is the takeaway.", kind="ending"),
    ]
    features = [
        SegmentFeatures(segment_id="h", total_score=0.9),
        SegmentFeatures(segment_id="b", total_score=0.8),
        SegmentFeatures(segment_id="e", total_score=0.85),
    ]
    out = ScoringService().generate_candidates(segments, features, top_k=5, min_score=0.1)
    assert out
