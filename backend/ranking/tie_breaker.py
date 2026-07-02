from __future__ import annotations

from backend.ranking.models import RankedClip


def break_ties(ranked: list[RankedClip]) -> list[RankedClip]:
    for i in range(len(ranked)):
        for j in range(i + 1, len(ranked)):
            if abs(ranked[i].final_score - ranked[j].final_score) < 0.001:
                if ranked[i].overall_confidence < ranked[j].overall_confidence:
                    ranked[i], ranked[j] = ranked[j], ranked[i]
                elif ranked[i].overall_confidence == ranked[j].overall_confidence:
                    if ranked[i].stage_scores.get("hook_quality", 0) < ranked[j].stage_scores.get("hook_quality", 0):
                        ranked[i], ranked[j] = ranked[j], ranked[i]
                    elif ranked[i].stage_scores.get("hook_quality", 0) == ranked[j].stage_scores.get("hook_quality", 0):
                        if ranked[i].candidate.duration > ranked[j].candidate.duration:
                            ranked[i], ranked[j] = ranked[j], ranked[i]
                        elif ranked[i].candidate.duration == ranked[j].candidate.duration:
                            if ranked[i].candidate.hook_start > ranked[j].candidate.hook_start:
                                ranked[i], ranked[j] = ranked[j], ranked[i]
    return ranked
