from __future__ import annotations

from backend.models.feature import SegmentFeatures
from backend.models.graph import GraphEdge, GraphNode, KnowledgeGraph
from backend.models.segment import AtomicSegment


class GraphService:
    def build_graph(self, segments: list[AtomicSegment], features: list[SegmentFeatures]) -> KnowledgeGraph:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        feature_map = {f.segment_id: f for f in features}

        for segment in segments:
            nodes.append(
                GraphNode(
                    id=segment.id,
                    label=segment.kind,
                    kind="segment",
                    metadata={
                        "start": segment.start,
                        "end": segment.end,
                        "score": feature_map.get(segment.id).total_score if segment.id in feature_map else segment.score,
                    },
                )
            )

        for left, right in zip(segments, segments[1:]):
            edges.append(GraphEdge(source=left.id, target=right.id, relation="next"))

        return KnowledgeGraph(nodes=nodes, edges=edges)
