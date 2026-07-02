from __future__ import annotations

import math

from backend.ranking.models import Candidate
from backend.config.ranking_config import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MODERATE,
    CONFIDENCE_LOW,
    CONFIDENCE_ELIMINATE,
)


def compute_confidence(
    audio_energy_source: str = "text_heuristic",
    non_fallback_count: int = 0,
    transcription_confidence: float | None = None,
    duration_seconds: float = 0.0,
) -> float:
    signals: list[float] = []

    if audio_energy_source == "real":
        signals.append(0.95)
    else:
        signals.append(0.45)

    completeness = non_fallback_count / 4.0
    signals.append(completeness)

    if transcription_confidence is not None:
        signals.append(transcription_confidence)
    else:
        signals.append(0.6)

    if 2.0 <= duration_seconds <= 30.0:
        signals.append(0.9)
    elif 1.0 <= duration_seconds <= 60.0:
        signals.append(0.7)
    else:
        signals.append(0.4)

    return round(sum(signals) / len(signals), 4)


def confidence_weighted_score(score: float, confidence: float) -> float:
    return round(score * confidence + 0.5 * (1 - confidence), 4)


def get_confidence_level(confidence: float) -> str:
    if confidence >= CONFIDENCE_HIGH:
        return "high"
    elif confidence >= CONFIDENCE_MODERATE:
        return "moderate"
    elif confidence >= CONFIDENCE_LOW:
        return "low"
    else:
        return "no_trust"
