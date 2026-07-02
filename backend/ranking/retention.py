from __future__ import annotations

from backend.ranking.models import Candidate
from backend.config.ranking_config import RETENTION_IDEAL_MIN, RETENTION_IDEAL_MAX, RETENTION_ACCEPTABLE_MIN, RETENTION_ACCEPTABLE_MAX


def stage_retention_prediction(candidates: list[Candidate]) -> list[Candidate]:
    for c in candidates:
        retention_score = 0.0
        confidence_signals: list[float] = []

        if RETENTION_IDEAL_MIN <= c.duration <= RETENTION_IDEAL_MAX:
            retention_score += 0.3
            confidence_signals.append(0.85)
        elif RETENTION_ACCEPTABLE_MIN <= c.duration <= RETENTION_ACCEPTABLE_MAX:
            retention_score += 0.2
            confidence_signals.append(0.7)
        elif 15 <= c.duration <= 90:
            retention_score += 0.1
            confidence_signals.append(0.5)
        else:
            retention_score += 0.0
            confidence_signals.append(0.3)

        ending_words = c.ending_text.lower().split()
        has_cta = any(w in ending_words for w in ["subscribe", "follow", "like", "comment", "share"])
        has_summary = any(w in ending_words for w in ["so", "therefore", "that's", "basically"])
        if has_cta or has_summary:
            retention_score += 0.25
            confidence_signals.append(0.8)
        else:
            retention_score += 0.1
            confidence_signals.append(0.5)

        retention_score += c.flow_score * 0.25
        confidence_signals.append(0.7)

        gap = c.body_start - c.hook_end
        if gap < 1:
            retention_score += 0.2
            confidence_signals.append(0.9)
        elif gap < 3:
            retention_score += 0.15
            confidence_signals.append(0.75)
        else:
            retention_score += 0.05
            confidence_signals.append(0.4)

        c.retention_score = round(min(1.0, retention_score), 4)
        c.retention_confidence = round(
            sum(confidence_signals) / len(confidence_signals), 4
        ) if confidence_signals else 0.5

    return candidates
