# backend/core/v101_bridge.py

import time
from typing import Any
from backend.core.artifact import Artifact, generate_deterministic_id, compute_output_hash
from backend.core.context import PipelineContext
from backend.models.data import TranscriptData, SignalData, GraphData, CandidatesData, ScoresData, PortfolioData


def segments_to_graph_artifact(segments: list) -> Artifact[GraphData]:
    """Convert production pipeline segments to Artifact[GraphData] for strategies."""
    nodes = []
    edges = []
    for i, seg in enumerate(segments):
        if hasattr(seg, "model_dump"):
            seg_dict = seg.model_dump(mode="json")
        elif isinstance(seg, dict):
            seg_dict = seg
        else:
            seg_dict = {"id": str(i), "text": getattr(seg, "text", ""), "start": getattr(seg, "start", 0), "end": getattr(seg, "end", 0)}

        node = {
            "id": seg_dict.get("id", f"node_{i}"),
            "text": seg_dict.get("text", ""),
            "start": seg_dict.get("start", 0),
            "end": seg_dict.get("end", 0),
            "segment_id": seg_dict.get("id", f"seg_{i}"),
        }
        nodes.append(node)
        if i > 0:
            edges.append({"source": f"node_{i-1}", "target": f"node_{i}", "type": "temporal"})

    graph_data = GraphData(nodes=nodes, edges=edges, node_count=len(nodes), edge_count=len(edges))
    output_hash = compute_output_hash(graph_data)
    return Artifact(
        artifact_id=generate_deterministic_id("", "graph_bridge", 1, output_hash=output_hash),
        version=1, created_at=time.time(),
        data=graph_data,
    )


def segments_to_signal_artifact(segments: list) -> Artifact[SignalData]:
    """Convert production pipeline segments to Artifact[SignalData] for window splitter."""
    seg_dicts = []
    for seg in segments:
        if hasattr(seg, "model_dump"):
            seg_dicts.append(seg.model_dump(mode="json"))
        elif isinstance(seg, dict):
            seg_dicts.append(seg)
        else:
            seg_dicts.append({"id": getattr(seg, "id", ""), "text": getattr(seg, "text", ""), "start": getattr(seg, "start", 0), "end": getattr(seg, "end", 0)})

    signal_data = SignalData(segments=seg_dicts, signal_count=len(seg_dicts))
    output_hash = compute_output_hash(signal_data)
    return Artifact(
        artifact_id=generate_deterministic_id("", "signal_bridge", 1, output_hash=output_hash),
        version=1, created_at=time.time(),
        data=signal_data,
    )


def candidates_to_scores_artifact(candidates: list) -> Artifact[ScoresData]:
    """Convert production pipeline ClipCandidate list to Artifact[ScoresData]."""
    scored = []
    for c in candidates:
        if hasattr(c, "model_dump"):
            c_dict = c.model_dump(mode="json")
        elif isinstance(c, dict):
            c_dict = c
        else:
            c_dict = {"id": getattr(c, "id", ""), "total_score": getattr(c, "total_score", 0)}

        scored.append({
            "id": c_dict.get("id", ""),
            "hook_text": c_dict.get("hook_text", ""),
            "body_text": c_dict.get("body_text", ""),
            "ending_text": c_dict.get("ending_text", ""),
            "start": c_dict.get("hook_start", 0),
            "end": c_dict.get("ending_end", 0),
            "duration": c_dict.get("duration", 0),
            "total_score": c_dict.get("total_score", 0),
            "event_ids": [c_dict.get("id", "")],
        })

    scores_data = ScoresData(scored_candidates=scored, objective_scores={}, score_distribution={})
    output_hash = compute_output_hash(scores_data)
    return Artifact(
        artifact_id=generate_deterministic_id("", "scores_bridge", 1, output_hash=output_hash),
        version=1, created_at=time.time(),
        data=scores_data,
    )


def build_pipeline_context(
    segments: list,
    graph_artifact: Artifact[GraphData],
    signal_artifact: Artifact[SignalData] = None,
) -> PipelineContext:
    """Build PipelineContext that strategies expect."""
    return PipelineContext(
        graph=graph_artifact,
        signals=signal_artifact,
    )


def merge_strategy_results(results: list[Artifact[CandidatesData]]) -> list[dict]:
    """Merge candidates from multiple strategy artifacts into a single list."""
    all_candidates = []
    strategies_used = []
    for artifact in results:
        if artifact and artifact.data:
            all_candidates.extend(artifact.data.candidates or [])
            strategies_used.extend(artifact.data.strategies_used or [])
    return all_candidates, strategies_used


def objective_results_to_scores(
    objective_results: dict,
    candidate: dict,
) -> dict:
    """Convert objective results dict to a scoring summary."""
    scores = {}
    total = 0.0
    count = 0
    for obj_id, result in objective_results.items():
        scores[obj_id] = {
            "score": result.score,
            "confidence": result.confidence,
            "status": result.status,
            "latency_ms": result.latency_ms,
        }
        total += result.score
        count += 1

    avg = total / count if count > 0 else 0.0
    return {"objective_scores": scores, "overall_score": avg, "objective_count": count}
