from __future__ import annotations

from backend.ranking.models import RankedClip


def generate_explanation(ranked: RankedClip, all_ranked: list[RankedClip]) -> str:
    parts: list[str] = []

    parts.append(
        f"Rank #{ranked.rank} with score {ranked.final_score} "
        f"(confidence: {ranked.overall_confidence})"
    )

    if ranked.stage_scores:
        best_stage = max(ranked.stage_scores, key=ranked.stage_scores.get)
        parts.append(f"Strongest signal: {best_stage} ({ranked.stage_scores[best_stage]})")

        worst_stage = min(ranked.stage_scores, key=ranked.stage_scores.get)
        parts.append(f"Weakest signal: {worst_stage} ({ranked.stage_scores[worst_stage]})")

    if ranked.rank < len(all_ranked):
        next_ranked = all_ranked[ranked.rank]
        diff = ranked.final_score - next_ranked.final_score
        parts.append(f"Leads next candidate by {diff:.4f}")

    eliminated_below = sum(
        1 for r in all_ranked[ranked.rank:]
        if hasattr(r.candidate, "eliminated_at") and r.candidate.eliminated_at
    )
    if eliminated_below > 0:
        parts.append(f"{eliminated_below} candidates eliminated before this clip")

    return " | ".join(parts)
