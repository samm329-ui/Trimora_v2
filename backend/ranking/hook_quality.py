from __future__ import annotations

from backend.ranking.models import Candidate
from backend.config.ranking_config import HOOK_IDEAL_MIN, HOOK_IDEAL_MAX, HOOK_ACCEPTABLE_MIN, HOOK_ACCEPTABLE_MAX

_CURIOSITY_WORDS = ["secret", "truth", "why", "how", "never", "always", "actually"]


def stage_hook_quality(candidates: list[Candidate]) -> list[Candidate]:
    for c in candidates:
        hook_score = 0.0
        confidence_signals: list[float] = []

        hook_duration = c.hook_end - c.hook_start
        if HOOK_IDEAL_MIN <= hook_duration <= HOOK_IDEAL_MAX:
            hook_score += 0.25
            confidence_signals.append(0.9)
        elif HOOK_ACCEPTABLE_MIN <= hook_duration <= HOOK_ACCEPTABLE_MAX:
            hook_score += 0.15
            confidence_signals.append(0.7)
        else:
            hook_score += 0.05
            confidence_signals.append(0.4)

        if "?" in c.hook_text:
            hook_score += 0.25
            confidence_signals.append(0.95)

        if "you" in c.hook_text.lower().split():
            hook_score += 0.15
            confidence_signals.append(0.85)

        if any(w in c.hook_text.lower() for w in _CURIOSITY_WORDS):
            hook_score += 0.2
            confidence_signals.append(0.8)

        word_count = len(c.hook_text.split())
        if word_count <= 10:
            hook_score += 0.15
            confidence_signals.append(0.9)
        elif word_count <= 15:
            hook_score += 0.1
            confidence_signals.append(0.75)
        else:
            hook_score += 0.05
            confidence_signals.append(0.5)

        c.hook_quality_score = round(min(1.0, hook_score), 4)
        c.hook_quality_confidence = round(
            sum(confidence_signals) / len(confidence_signals), 4
        ) if confidence_signals else 0.5

    return candidates
