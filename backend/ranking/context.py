from __future__ import annotations

from backend.ranking.models import Candidate
from backend.config.ranking_config import CONTEXT_PENALTY_THRESHOLD, CONTEXT_PENALTY_FACTOR

_STOP_WORDS = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for", "of", "and", "or", "but", "it", "that", "this", "with", "as", "by", "from", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "can", "could", "may", "might", "shall", "should", "not", "no", "nor", "so", "if", "then", "than", "too", "very", "just", "about", "also", "more", "some", "any", "each", "every", "all", "both", "few", "most", "other", "into", "over", "such", "only", "own", "same", "than"}

_PRONOUNS = {"he", "she", "it", "they", "him", "her", "his", "their"}


def stage_context_validation(candidates: list[Candidate]) -> list[Candidate]:
    for c in candidates:
        context_score = 0.0

        gap1 = c.body_start - c.hook_end
        gap2 = c.ending_start - c.body_end
        avg_gap = (gap1 + gap2) / 2
        if avg_gap < 2:
            context_score += 0.4
        elif avg_gap < 5:
            context_score += 0.3
        elif avg_gap < 10:
            context_score += 0.2
        else:
            context_score += 0.1

        hook_pronouns = _PRONOUNS & set(c.hook_text.lower().split())
        body_pronouns = _PRONOUNS & set(c.body_text.lower().split())
        if hook_pronouns and body_pronouns and not (hook_pronouns & body_pronouns):
            context_score += 0.0
        else:
            context_score += 0.3

        hook_nouns = set(c.hook_text.lower().split()) - _STOP_WORDS
        body_nouns = set(c.body_text.lower().split()) - _STOP_WORDS
        if hook_nouns & body_nouns:
            context_score += 0.3
        else:
            context_score += 0.1

        c.context_score = round(min(1.0, context_score), 4)
        c.context_confidence = 0.75

    for c in candidates:
        if c.context_score < CONTEXT_PENALTY_THRESHOLD:
            c.raw_score *= CONTEXT_PENALTY_FACTOR

    return candidates
