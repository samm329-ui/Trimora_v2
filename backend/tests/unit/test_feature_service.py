from backend.services.feature_service import FeatureService
from backend.models.segment import AtomicSegment


def test_compute_features_default():
    segment = AtomicSegment(id="seg_1", start=0.0, end=5.0, text="What if everything you know is wrong?", kind="hook", order=0)
    svc = FeatureService()
    features = svc.compute_features(segment)
    assert features.segment_id == "seg_1"
    assert 0.0 <= features.audio_intensity <= 1.0
    assert 0.0 <= features.text_density <= 1.0
    assert 0.0 <= features.structure_score <= 1.0
    assert 0.0 <= features.pattern_score <= 1.0
    assert 0.0 <= features.total_score <= 1.0
    assert features.audio_energy_source == "text_heuristic"
    assert "word_count" in features.extras


def test_compute_features_hook_structure():
    svc = FeatureService()
    short_hook = AtomicSegment(id="h1", start=0.0, end=3.0, text="What if?", kind="hook", order=0)
    long_hook = AtomicSegment(id="h2", start=0.0, end=15.0, text="This is a very long hook that keeps going and going without stopping at all", kind="hook", order=1)
    f1 = svc.compute_features(short_hook)
    f2 = svc.compute_features(long_hook)
    assert f1.structure_score > f2.structure_score


def test_compute_features_body_structure():
    svc = FeatureService()
    ideal = AtomicSegment(id="b1", start=0.0, end=30.0, text="This is a body segment with ideal duration for content.", kind="body", order=0)
    too_short = AtomicSegment(id="b2", start=0.0, end=2.0, text="Too short.", kind="body", order=1)
    f1 = svc.compute_features(ideal)
    f2 = svc.compute_features(too_short)
    assert f1.structure_score > f2.structure_score


def test_compute_features_ending_structure():
    svc = FeatureService()
    concise = AtomicSegment(id="e1", start=0.0, end=5.0, text="So that is the takeaway.", kind="ending", order=0)
    long = AtomicSegment(id="e2", start=0.0, end=20.0, text="This is a very long ending that just keeps going and going without wrapping up.", kind="ending", order=1)
    f1 = svc.compute_features(concise)
    f2 = svc.compute_features(long)
    assert f1.structure_score > f2.structure_score


def test_compute_features_pattern_bonus():
    svc = FeatureService()
    with_question = AtomicSegment(id="p1", start=0.0, end=3.0, text="What if this works?", kind="hook", order=0)
    with_numbers = AtomicSegment(id="p2", start=0.0, end=3.0, text="There are 5 reasons to try this.", kind="hook", order=1)
    f1 = svc.compute_features(with_question)
    f2 = svc.compute_features(with_numbers)
    assert f1.pattern_score >= 0.5
    assert f2.pattern_score >= 0.5


def test_compute_features_audio_energy_tracking():
    svc = FeatureService()
    segment = AtomicSegment(id="s1", start=0.0, end=5.0, text="Test segment text here.", kind="body", order=0)
    features = svc.compute_features(segment)
    assert features.audio_energy is None
    assert features.audio_energy_source == "text_heuristic"
