# backend/optimization/narrative.py

from backend.core.artifact import Artifact, generate_deterministic_id, compute_output_hash
from backend.models.data import CandidatesData
import time


class NarrativeOptimizer:
    """Reorders candidates for narrative flow."""

    async def execute(self, inputs: dict) -> Artifact[CandidatesData]:
        key = list(inputs.keys())[0] if inputs else None
        artifact = inputs.get(key) if key else None
        if artifact is None:
            raise ValueError("NarrativeOptimizer requires an input artifact")

        candidates = artifact.data.candidates if hasattr(artifact.data, 'candidates') else []

        # Sort by start time for narrative coherence
        sorted_candidates = sorted(candidates, key=lambda c: c.get("start", 0))

        output_data = CandidatesData(
            candidates=sorted_candidates,
            candidate_count=len(sorted_candidates),
            strategies_used=artifact.data.strategies_used if hasattr(artifact.data, 'strategies_used') else [],
        )
        output_hash = compute_output_hash(output_data)
        parent_hash = artifact.compute_hash()

        return Artifact(
            artifact_id=generate_deterministic_id(parent_hash, "narrative", 1, output_hash=output_hash),
            version=1, created_at=time.time(),
            parent_id=artifact.artifact_id, parent_hash=parent_hash,
            data=output_data,
        )
