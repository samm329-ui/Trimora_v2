# backend/optimization/narrative.py

from backend.core.artifact import Artifact, ArtifactStage, PipelineContractError, create_artifact
from backend.models.data import ScoresData


class NarrativeOptimizer:
    """Reorders candidates for narrative flow."""

    INPUT_TYPE = ScoresData
    OUTPUT_TYPE = ScoresData

    async def execute(self, inputs: dict) -> Artifact[ScoresData]:
        key = list(inputs.keys())[0] if inputs else None
        artifact = inputs.get(key) if key else None
        if artifact is None:
            raise ValueError("NarrativeOptimizer requires an input artifact")

        if not isinstance(artifact.data, self.INPUT_TYPE):
            raise PipelineContractError(
                ArtifactStage.NARRATIVE, self.INPUT_TYPE, type(artifact.data),
                artifact.artifact_id, artifact.parent_id,
            )

        scored = artifact.data.scored_candidates
        sorted_scored = sorted(scored, key=lambda c: c.get("start", 0))

        output_data = ScoresData(
            scored_candidates=sorted_scored,
            objective_scores=artifact.data.objective_scores,
            score_distribution=artifact.data.score_distribution,
        )

        return create_artifact(
            data=output_data,
            stage=ArtifactStage.NARRATIVE,
            parent=artifact,
        )
