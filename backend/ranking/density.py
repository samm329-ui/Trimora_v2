from __future__ import annotations

from backend.ranking.models import Candidate
from backend.config.ranking_config import DENSITY_IDEAL_MIN, DENSITY_IDEAL_MAX, DENSITY_ACCEPTABLE_MIN, DENSITY_ACCEPTABLE_MAX


def stage_information_density(candidates: list[Candidate]) -> list[Candidate]:
    for c in candidates:
        total_words = len(
            (c.hook_text + " " + c.body_text + " " + c.ending_text).split()
        )
        wps = total_words / max(c.duration, 0.1)

        if DENSITY_IDEAL_MIN <= wps <= DENSITY_IDEAL_MAX:
            density_score = 0.9
        elif DENSITY_ACCEPTABLE_MIN <= wps <= DENSITY_ACCEPTABLE_MAX:
            density_score = 0.7
        elif 1.0 <= wps <= 5.0:
            density_score = 0.5
        else:
            density_score = 0.3

        specificity = 0.0
        all_text = c.hook_text + " " + c.body_text + " " + c.ending_text
        if any(cd.isdigit() for cd in all_text):
            specificity += 0.1
        if any(w[0].isupper() for w in all_text.split() if len(w) > 2):
            specificity += 0.05

        c.density_score = round(min(1.0, density_score + specificity), 4)
        c.density_confidence = 0.8

    return candidates
