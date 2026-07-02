from __future__ import annotations

from backend.ranking.models import Candidate
from backend.services.embedding_service import EmbeddingService
from backend.config.ranking_config import NARRATIVE_PENALTY_THRESHOLD, NARRATIVE_PENALTY_FACTOR

_STOP_WORDS = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for", "of", "and", "or", "but", "it", "that", "this", "with", "as", "by", "from", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "can", "could", "may", "might", "shall", "should", "not", "no", "nor", "so", "if", "then", "than", "too", "very", "just", "about", "also", "more", "some", "any", "each", "every", "all", "both", "few", "most", "other", "into", "over", "such", "only", "own", "same", "than"}


def stage_narrative_validation(candidates: list[Candidate], embedder: EmbeddingService) -> list[Candidate]:
    for c in candidates:
        narrative_score = 0.0
        confidence_signals: list[float] = []

        hook_emb = embedder.embed(c.hook_text)
        body_emb = embedder.embed(c.body_text)
        ending_emb = embedder.embed(c.ending_text)

        hook_body_similarity = embedder.cosine_similarity(hook_emb, body_emb)
        body_ending_similarity = embedder.cosine_similarity(body_emb, ending_emb)

        semantic_score = 0.0
        if hook_body_similarity > 0.4:
            semantic_score += 0.35
        elif hook_body_similarity > 0.2:
            semantic_score += 0.20
        else:
            semantic_score += 0.05

        if body_ending_similarity > 0.3:
            semantic_score += 0.25
        elif body_ending_similarity > 0.15:
            semantic_score += 0.15
        else:
            semantic_score += 0.05

        hook_magnitude = embedder.vector_magnitude(hook_emb)
        body_magnitude = embedder.vector_magnitude(body_emb)
        if body_magnitude > hook_magnitude * 0.8:
            semantic_score += 0.15
        else:
            semantic_score += 0.05

        narrative_score += min(0.6, semantic_score)
        confidence_signals.append(0.9 if hook_body_similarity > 0.3 else 0.6)

        hook_words = set(c.hook_text.lower().split())
        body_words = set(c.body_text.lower().split())
        overlap = len(hook_words & body_words)
        body_ratio = overlap / max(len(hook_words), 1)

        if body_ratio > 0.3 and hook_body_similarity > 0.3:
            narrative_score += 0.15
        elif body_ratio > 0.1:
            narrative_score += 0.08
        confidence_signals.append(min(0.8, 0.5 + body_ratio))

        hook_has_question = "?" in c.hook_text
        hook_has_claim = any(w in c.hook_text.lower() for w in [
            "secret", "truth", "fact", "proof", "reason", "why",
        ])
        if hook_has_question or hook_has_claim:
            narrative_score += 0.15
            confidence_signals.append(0.85)
        else:
            narrative_score += 0.05
            confidence_signals.append(0.5)

        ending_starts_with_new = any(
            c.ending_text.lower().startswith(w)
            for w in ["but", "however", "also", "another", "speaking of"]
        )
        if not ending_starts_with_new:
            narrative_score += 0.10
            confidence_signals.append(0.8)
        else:
            narrative_score += 0.02
            confidence_signals.append(0.45)

        c.narrative_score = round(min(1.0, narrative_score), 4)
        c.narrative_confidence = round(sum(confidence_signals) / len(confidence_signals), 4) if confidence_signals else 0.5

    for c in candidates:
        if c.narrative_score < NARRATIVE_PENALTY_THRESHOLD:
            c.raw_score *= NARRATIVE_PENALTY_FACTOR

    return candidates
