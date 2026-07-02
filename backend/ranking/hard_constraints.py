from __future__ import annotations

from backend.ranking.models import Candidate
from backend.config.ranking_config import (
    MIN_DURATION_SECONDS,
    MAX_DURATION_SECONDS,
    MAX_GAP_SECONDS,
    MIN_RAW_SCORE,
)


def stage_hard_constraints(candidates: list[Candidate]) -> list[Candidate]:
    passed: list[Candidate] = []
    for c in candidates:
        reasons: list[str] = []

        if c.duration < MIN_DURATION_SECONDS:
            reasons.append("duration_too_short")
        elif c.duration > MAX_DURATION_SECONDS:
            reasons.append("duration_too_long")

        if not (c.hook_start <= c.body_start <= c.ending_start):
            reasons.append("non_chronological")

        if c.hook_end > c.body_start or c.body_end > c.ending_start:
            reasons.append("segment_overlap")

        gap1 = c.body_start - c.hook_end
        gap2 = c.ending_start - c.body_end
        if gap1 > MAX_GAP_SECONDS or gap2 > MAX_GAP_SECONDS:
            reasons.append("excessive_gap")

        if c.raw_score < MIN_RAW_SCORE:
            reasons.append("score_too_low")

        if reasons:
            c.eliminated_at = "hard_constraints"
            c.elimination_reasons = reasons
        else:
            passed.append(c)

    return passed
