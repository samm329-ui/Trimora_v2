from __future__ import annotations

import numpy as np

from backend.ranking.models import Candidate, RankedClip
from backend.ranking.explanation import generate_explanation
from backend.services.embedding_service import EmbeddingService
from backend.config.ranking_config import (
    GLOBAL_OPTIMIZATION_LAMBDA_QUALITY,
    GLOBAL_OPTIMIZATION_LAMBDA_DIVERSITY,
    GLOBAL_OPTIMIZATION_TOP_K,
)


def stage_global_optimization(
    candidates: list[RankedClip],
    embedder: EmbeddingService,
    top_k: int = GLOBAL_OPTIMIZATION_TOP_K,
    lambda_quality: float = GLOBAL_OPTIMIZATION_LAMBDA_QUALITY,
    lambda_diversity: float = GLOBAL_OPTIMIZATION_LAMBDA_DIVERSITY,
) -> list[RankedClip]:
    if len(candidates) <= top_k:
        for i, r in enumerate(candidates):
            r.rank = i + 1
            r.explanation = generate_explanation(r, candidates)
        return candidates

    embeddings = np.array([
        embedder.embed(
            f"{r.candidate.hook_text} {r.candidate.body_text} {r.candidate.ending_text}"
        )
        for r in candidates
    ])

    selected: list[int] = []
    remaining: list[int] = list(range(len(candidates)))

    for _ in range(top_k):
        best_idx = -1
        best_mmr = -float("inf")

        for i in remaining:
            quality = candidates[i].final_score

            if selected:
                similarities = [
                    embedder.cosine_similarity(embeddings[i], embeddings[j])
                    for j in selected
                ]
                max_sim = max(similarities)
            else:
                max_sim = 0.0

            mmr = lambda_quality * quality - lambda_diversity * max_sim

            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = i

        if best_idx == -1:
            break

        selected.append(best_idx)
        remaining.remove(best_idx)

    result = [candidates[i] for i in selected]
    result.sort(key=lambda r: r.final_score, reverse=True)

    for i, r in enumerate(result):
        r.rank = i + 1
        r.explanation = generate_explanation(r, result)

    return result
