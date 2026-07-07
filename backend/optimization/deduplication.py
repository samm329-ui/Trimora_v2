# backend/optimization/deduplication.py

from abc import ABC, abstractmethod
from backend.core.artifact import Artifact, generate_deterministic_id, compute_output_hash
from backend.models.data import CandidatesData
import time


class SimilarityProvider(ABC):
    """Interface for deduplication similarity — not hardcoded Jaccard."""

    @abstractmethod
    def compute(self, c1: dict, c2: dict) -> float:
        pass


class JaccardSimilarity(SimilarityProvider):
    def compute(self, c1: dict, c2: dict) -> float:
        events1 = set(c1.get("event_ids", []))
        events2 = set(c2.get("event_ids", []))
        if not events1 or not events2:
            return 0.0
        return len(events1 & events2) / len(events1 | events2)


class CandidateDeduplicationService:
    def __init__(self, threshold: float = 0.5, similarity_provider: SimilarityProvider = None):
        self.threshold = threshold
        self.similarity = similarity_provider or JaccardSimilarity()

    async def execute(self, inputs: dict) -> Artifact[CandidatesData]:
        key = list(inputs.keys())[0] if inputs else None
        artifact = inputs.get(key) if key else None
        if artifact is None:
            raise ValueError("CandidateDeduplicationService requires an input artifact")

        candidates = artifact.data.candidates if hasattr(artifact.data, 'candidates') else []
        if not candidates:
            output_data = CandidatesData(candidates=[], candidate_count=0, strategies_used=[])
            output_hash = compute_output_hash(output_data)
            return Artifact(
                artifact_id=generate_deterministic_id(artifact.compute_hash(), "dedup", 1, output_hash=output_hash),
                version=1, created_at=time.time(),
                parent_id=artifact.artifact_id, parent_hash=artifact.compute_hash(),
                data=output_data,
            )

        keep = []
        removed = []
        for cand in candidates:
            is_dup = False
            for kept in keep:
                sim = self.similarity.compute(cand, kept)
                if sim >= self.threshold:
                    is_dup = True
                    removed.append({"candidate_id": cand.get("id"), "similar_to": kept.get("id"), "similarity": sim})
                    break
            if not is_dup:
                keep.append(cand)

        output_data = CandidatesData(
            candidates=keep,
            candidate_count=len(keep),
            strategies_used=artifact.data.strategies_used if hasattr(artifact.data, 'strategies_used') else [],
            deduplication_result={"removed": removed, "original_count": len(candidates), "final_count": len(keep)},
        )
        output_hash = compute_output_hash(output_data)

        return Artifact(
            artifact_id=generate_deterministic_id(artifact.compute_hash(), "dedup", 1, output_hash=output_hash),
            version=1, created_at=time.time(),
            parent_id=artifact.artifact_id, parent_hash=artifact.compute_hash(),
            data=output_data,
        )
