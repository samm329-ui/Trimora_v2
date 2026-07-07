# backend/optimization/portfolio.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
import time
from backend.core.artifact import Artifact, generate_deterministic_id, compute_output_hash
from backend.models.data import ScoresData, PortfolioData


class SimilarityProvider(ABC):
    """Interface for candidate similarity — not hardcoded Jaccard."""

    @abstractmethod
    def compute(self, c1: dict, c2: dict) -> float:
        """Returns similarity score between 0 and 1."""
        pass


class JaccardSimilarity(SimilarityProvider):
    """Default Jaccard similarity on event_ids."""

    def compute(self, c1: dict, c2: dict) -> float:
        events1 = set(c1.get("event_ids", []))
        events2 = set(c2.get("event_ids", []))
        if not events1 or not events2:
            return 0.0
        return len(events1 & events2) / len(events1 | events2)


class DiversityPolicy:
    BALANCED = "balanced"
    QUALITY_FOCUSED = "quality"
    DIVERSITY_FOCUSED = "diversity"
    SIMILAR_OK = "similar"


class PortfolioOptimizer:
    def __init__(self, top_k: int = 20, policy: str = DiversityPolicy.BALANCED,
                 similarity_provider: SimilarityProvider = None):
        self.top_k = top_k
        self.policy = policy
        self.similarity = similarity_provider or JaccardSimilarity()
        self._policies = {
            DiversityPolicy.BALANCED: (0.7, 0.3),
            DiversityPolicy.QUALITY_FOCUSED: (0.85, 0.15),
            DiversityPolicy.DIVERSITY_FOCUSED: (0.5, 0.5),
            DiversityPolicy.SIMILAR_OK: (0.9, 0.1),
        }

    async def execute(self, inputs: dict) -> Artifact[PortfolioData]:
        key = list(inputs.keys())[0] if inputs else None
        artifact = inputs.get(key) if key else None
        if artifact is None:
            raise ValueError("PortfolioOptimizer requires an input artifact")

        scores = artifact.data
        if not scores.scored_candidates:
            output_data = PortfolioData()
            output_hash = compute_output_hash(output_data)
            return Artifact(
                artifact_id=generate_deterministic_id(artifact.compute_hash(), "portfolio", 1, output_hash=output_hash),
                version=1, created_at=time.time(),
                parent_id=artifact.artifact_id, parent_hash=artifact.compute_hash(),
                data=output_data,
            )

        lambda_q, lambda_d = self._policies.get(self.policy, (0.7, 0.3))
        selected = self._mmr_select(scores.scored_candidates, lambda_q, lambda_d)
        rejected_count = len(scores.scored_candidates) - len(selected)

        output_data = PortfolioData(
            portfolio={"clips": selected}, selected_count=len(selected),
            rejected_count=rejected_count,
            total_score=sum(c.get("overall_score", 0) for c in selected) / max(len(selected), 1),
            diversity_score=self._compute_diversity(selected),
        )
        output_hash = compute_output_hash(output_data)

        return Artifact(
            artifact_id=generate_deterministic_id(artifact.compute_hash(), "portfolio", 1, output_hash=output_hash),
            version=1, created_at=time.time(),
            parent_id=artifact.artifact_id, parent_hash=artifact.compute_hash(),
            data=output_data,
        )

    def _mmr_select(self, candidates: list, lambda_q: float, lambda_d: float) -> list:
        if len(candidates) <= self.top_k:
            return candidates

        sorted_cands = sorted(candidates, key=lambda c: c.get("overall_score", 0), reverse=True)
        selected = [sorted_cands[0]]
        remaining = sorted_cands[1:]

        while len(selected) < self.top_k and remaining:
            best_score = -1
            best_idx = 0
            for i, cand in enumerate(remaining):
                quality = cand.get("overall_score", 0)
                max_sim = max(self.similarity.compute(cand, s) for s in selected) if selected else 0
                mmr = lambda_q * quality - lambda_d * max_sim
                if mmr > best_score:
                    best_score = mmr
                    best_idx = i
            selected.append(remaining.pop(best_idx))
        return selected

    def _compute_diversity(self, selected: list) -> float:
        if len(selected) <= 1:
            return 1.0
        total_sim = 0
        count = 0
        for i in range(len(selected)):
            for j in range(i + 1, len(selected)):
                total_sim += self.similarity.compute(selected[i], selected[j])
                count += 1
        return 1.0 - (total_sim / max(count, 1))
