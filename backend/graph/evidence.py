# backend/graph/evidence.py

from backend.core.artifact import Artifact, generate_deterministic_id, compute_output_hash
from backend.models.data import EvidenceData, GraphData
import time


class EvidenceGraph:
    """Constructs evidence graph from signals."""

    async def execute(self, inputs: dict) -> Artifact[GraphData]:
        key = list(inputs.keys())[0] if inputs else None
        artifact = inputs.get(key) if key else None
        if artifact is None:
            raise ValueError("EvidenceGraph requires an input artifact")

        data = artifact.data
        raw_segments = data.segments if hasattr(data, 'segments') else []
        audio_signals = data.audio_signals if hasattr(data, 'audio_signals') else []

        # Flatten windows into individual segments
        segments = []
        for seg in raw_segments:
            if "segments" in seg and isinstance(seg["segments"], list):
                # This is a window — flatten its inner segments
                for inner in seg["segments"]:
                    segments.append(inner)
            else:
                segments.append(seg)

        nodes = []
        edges = []
        for i, seg in enumerate(segments):
            node = {
                "id": f"node_{i}",
                "text": seg.get("text", ""),
                "start": seg.get("start", 0),
                "end": seg.get("end", 0),
                "segment_id": seg.get("id", ""),
            }
            nodes.append(node)
            if i > 0:
                edges.append({"source": f"node_{i-1}", "target": f"node_{i}", "type": "temporal"})

        output_data = GraphData(
            nodes=nodes, edges=edges,
            node_count=len(nodes), edge_count=len(edges),
        )
        output_hash = compute_output_hash(output_data)
        parent_hash = artifact.compute_hash()

        return Artifact(
            artifact_id=generate_deterministic_id(parent_hash, "graph", 1, output_hash=output_hash),
            version=1, created_at=time.time(),
            parent_id=artifact.artifact_id, parent_hash=parent_hash,
            data=output_data,
        )
