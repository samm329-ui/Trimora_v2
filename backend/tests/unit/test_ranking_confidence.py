from backend.ranking.confidence import compute_confidence, confidence_weighted_score, get_confidence_level


def test_compute_confidence_real_audio():
    conf = compute_confidence(audio_energy_source="real", non_fallback_count=3, transcription_confidence=0.9, duration_seconds=15.0)
    assert 0.0 <= conf <= 1.0
    assert conf > 0.7


def test_compute_confidence_text_heuristic():
    conf = compute_confidence(audio_energy_source="text_heuristic", non_fallback_count=0, transcription_confidence=None, duration_seconds=5.0)
    assert 0.0 <= conf <= 1.0
    assert conf < 0.7


def test_compute_confidence_extreme_duration():
    conf = compute_confidence(audio_energy_source="text_heuristic", non_fallback_count=1, transcription_confidence=0.6, duration_seconds=120.0)
    assert 0.0 <= conf <= 1.0


def test_confidence_weighted_score_high():
    result = confidence_weighted_score(0.9, 0.95)
    assert result < 0.9
    assert result > 0.85


def test_confidence_weighted_score_low():
    result = confidence_weighted_score(0.9, 0.3)
    assert result < 0.7
    assert result > 0.5


def test_confidence_weighted_score_mid():
    result = confidence_weighted_score(0.5, 0.5)
    assert result == 0.5


def test_get_confidence_level_high():
    assert get_confidence_level(0.95) == "high"


def test_get_confidence_level_moderate():
    assert get_confidence_level(0.75) == "moderate"


def test_get_confidence_level_low():
    assert get_confidence_level(0.5) == "low"


def test_get_confidence_level_no_trust():
    assert get_confidence_level(0.2) == "no_trust"
