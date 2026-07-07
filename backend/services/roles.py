# backend/services/roles.py

from backend.core.artifact import Artifact, generate_deterministic_id, compute_output_hash
from backend.models.data import SignalData
import time


class DynamicRoleClassifier:
    """Classifies segments into roles (hook, body, ending, reaction)."""

    async def execute(self, inputs: dict) -> Artifact:
        key = list(inputs.keys())[0] if inputs else None
        artifact = inputs.get(key) if key else None
        if artifact is None:
            raise ValueError("DynamicRoleClassifier requires an input artifact")

        signals = artifact.data
        segments = signals.segments if hasattr(signals, 'segments') else []

        classified = []
        for i, seg in enumerate(segments):
            text = seg.get("text", "").lower()
            if i == 0 or "?" in text or any(w in text for w in ["secret", "truth", "why"]):
                role = "hook"
            elif i == len(segments) - 1 or any(w in text for w in ["so", "therefore", "subscribe"]):
                role = "ending"
            elif any(w in text for w in ["haha", "lol", "omg"]):
                role = "reaction"
            else:
                role = "body"
            classified.append({**seg, "role": role})

        output_data = {"classified_segments": classified, "role_count": len(classified)}
        output_hash = compute_output_hash(output_data)

        return Artifact(
            artifact_id=generate_deterministic_id(artifact.compute_hash(), "roles", 1, output_hash=output_hash),
            version=1, created_at=time.time(),
            parent_id=artifact.artifact_id, parent_hash=artifact.compute_hash(),
            data=output_data,
        )
