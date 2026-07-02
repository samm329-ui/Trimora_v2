from __future__ import annotations

import logging

from backend.ranking.models import Candidate, RankedClip, RankingResult
from backend.ranking.hard_constraints import stage_hard_constraints
from backend.ranking.narrative import stage_narrative_validation
from backend.ranking.context import stage_context_validation
from backend.ranking.hook_quality import stage_hook_quality
from backend.ranking.density import stage_information_density
from backend.ranking.retention import stage_retention_prediction
from backend.ranking.novelty import stage_novelty
from backend.ranking.optimizer import stage_global_optimization
from backend.ranking.tie_breaker import break_ties
from backend.ranking.confidence import compute_confidence, confidence_weighted_score
from backend.services.embedding_service import EmbeddingService
from backend.config.ranking_config import (
    RANKING_STAGE_WEIGHTS,
    FINAL_RANKING_RAW_SCORE_BOOST,
    FINAL_RANKING_STAGE_WEIGHT,
    GLOBAL_OPTIMIZATION_TOP_K,
)

logger = logging.getLogger(__name__)


class RankingEngine:
    def __init__(self, embedder: EmbeddingService | None = None):
        self.embedder = embedder or EmbeddingService()

    def _compute_final_ranking(self, candidates: list[Candidate]) -> list[RankedClip]:
        ranked: list[RankedClip] = []

        for c in candidates:
            stage_scores = {
                "hook_quality": getattr(c, "hook_quality_score", 0.0),
                "narrative": getattr(c, "narrative_score", 0.0),
                "context": getattr(c, "context_score", 0.0),
                "density": getattr(c, "density_score", 0.0),
                "retention": getattr(c, "retention_score", 0.0),
                "novelty": getattr(c, "novelty_score", 0.0),
            }
            stage_confidences = {
                "hook_quality": getattr(c, "hook_quality_confidence", 0.5),
                "narrative": getattr(c, "narrative_confidence", 0.5),
                "context": getattr(c, "context_confidence", 0.5),
                "density": getattr(c, "density_confidence", 0.5),
                "retention": getattr(c, "retention_confidence", 0.5),
                "novelty": getattr(c, "novelty_confidence", 0.5),
            }

            weighted_sum = 0.0
            confidence_sum = 0.0
            for stage in RANKING_STAGE_WEIGHTS:
                score = stage_scores[stage]
                conf = stage_confidences[stage]
                weight = RANKING_STAGE_WEIGHTS[stage]
                weighted_sum += score * conf * weight
                confidence_sum += conf * weight

            final_score = weighted_sum / max(confidence_sum, 0.001)
            overall_confidence = confidence_sum / sum(RANKING_STAGE_WEIGHTS.values())

            final_score = final_score * FINAL_RANKING_STAGE_WEIGHT + c.raw_score * FINAL_RANKING_RAW_SCORE_BOOST

            ranked.append(RankedClip(
                candidate=c,
                final_score=round(final_score, 4),
                overall_confidence=round(overall_confidence, 4),
                stage_scores=stage_scores,
                stage_confidences=stage_confidences,
                hook_quality_score=stage_scores["hook_quality"],
                hook_quality_confidence=stage_confidences["hook_quality"],
                narrative_score=stage_scores["narrative"],
                narrative_confidence=stage_confidences["narrative"],
                context_score=stage_scores["context"],
                context_confidence=stage_confidences["context"],
                density_score=stage_scores["density"],
                density_confidence=stage_confidences["density"],
                retention_score=stage_scores["retention"],
                retention_confidence=stage_confidences["retention"],
                novelty_score=stage_scores["novelty"],
                novelty_confidence=stage_confidences["novelty"],
            ))

        ranked.sort(key=lambda r: r.final_score, reverse=True)
        ranked = break_ties(ranked)

        return ranked

    def rank(
        self,
        candidates: list[Candidate],
        job_id: str = "",
        return_all: bool = False,
    ) -> RankingResult:
        total = len(candidates)

        passed = stage_hard_constraints(candidates)
        after_hard = len(passed)

        passed = stage_narrative_validation(passed, self.embedder)
        passed = stage_context_validation(passed)

        stage_hook_quality(passed)
        stage_information_density(passed)
        stage_retention_prediction(passed)
        stage_novelty(passed, self.embedder)

        ranked = self._compute_final_ranking(passed)

        optimized = stage_global_optimization(ranked, self.embedder)

        eliminated = []
        for c in candidates:
            if c.eliminated_at:
                eliminated.append({
                    "candidate_id": c.id,
                    "eliminated_at": c.eliminated_at,
                    "reasons": c.elimination_reasons,
                    "raw_score": c.raw_score,
                })

        result = RankingResult(
            job_id=job_id,
            total_candidates=total,
            after_hard_constraints=after_hard,
            after_global_optimization=len(optimized),
            final_ranked=len(optimized),
            ranked_clips=optimized,
            eliminated_clips=eliminated,
            ranking_config={
                "stage_weights": RANKING_STAGE_WEIGHTS,
                "confidence_threshold": 0.40,
                "tie_breaking": ["confidence", "hook_quality", "duration", "position"],
                "global_optimization": {
                    "lambda_quality": 0.7,
                    "lambda_diversity": 0.3,
                    "semantic_similarity_threshold": 0.75,
                },
                "pruning": {
                    "max_hooks": 15,
                    "max_bodies": 40,
                    "max_endings": 10,
                    "min_segment_score": 0.2,
                },
            },
        )

        self.embedder.clear_cache()
        return result
