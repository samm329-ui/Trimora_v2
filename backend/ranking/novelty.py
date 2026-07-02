from __future__ import annotations

import numpy as np

from backend.ranking.models import Candidate
from backend.services.embedding_service import EmbeddingService
from backend.config.ranking_config import SEMANTIC_SIMILARITY_THRESHOLD, NOVELTY_HOOK_THRESHOLD, NOVELTY_BODY_THRESHOLD


def stage_novelty(candidates: list[Candidate], embedder: EmbeddingService) -> list[Candidate]:
    if not candidates:
        return candidates

    candidates.sort(key=lambda c: c.raw_score, reverse=True)

    candidate_texts = [
        f"{c.hook_text} {c.body_text} {c.ending_text}" for c in candidates
    ]
    candidate_embeddings = embedder.embed_batch(candidate_texts)

    seen_embeddings: list[np.ndarray] = []

    for i, c in enumerate(candidates):
        emb = candidate_embeddings[i]

        is_semantic_dup = False
        max_similarity = 0.0
        for seen_emb in seen_embeddings:
            sim = embedder.cosine_similarity(emb, seen_emb)
            max_similarity = max(max_similarity, sim)
            if sim >= SEMANTIC_SIMILARITY_THRESHOLD:
                is_semantic_dup = True
                break

        if is_semantic_dup:
            c.novelty_score = max(0.1, 1.0 - max_similarity)
            c.novelty_confidence = 0.92
        else:
            timestamp_dup = False
            for seen_c in candidates[:i]:
                same_hook = abs(c.hook_start - seen_c.hook_start) < NOVELTY_HOOK_THRESHOLD
                same_body = abs(c.body_start - seen_c.body_start) < NOVELTY_BODY_THRESHOLD
                if same_hook and same_body:
                    timestamp_dup = True
                    break

            if timestamp_dup:
                c.novelty_score = 0.25
                c.novelty_confidence = 0.95
            else:
                c.novelty_score = 0.9
                c.novelty_confidence = 0.88
                seen_embeddings.append(emb)

    return candidates
