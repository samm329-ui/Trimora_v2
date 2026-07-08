# backend/strategies/builtin.py

from backend.strategies.base import ClipStrategy
from backend.core.artifact import Artifact, ArtifactStage, create_artifact
from backend.core.context import PipelineContext
from backend.models.data import CandidatesData


class StoryStrategy(ClipStrategy):
    def strategy_id(self) -> str:
        return "story"

    async def generate(self, context: PipelineContext) -> Artifact[CandidatesData]:
        graph_artifact = context.get("graph")
        graph = graph_artifact.data if graph_artifact else None
        candidates = []
        events = graph.nodes if graph else []

        for i in range(0, len(events) - 2, 2):
            hook = events[i]
            body = events[i + 1] if i + 1 < len(events) else events[i]
            ending = events[i + 2] if i + 2 < len(events) else events[-1]
            candidates.append({
                "id": f"story_{i}", "strategy": "story",
                "event_ids": [hook.get("id"), body.get("id"), ending.get("id")],
                "start": hook.get("start", 0), "end": ending.get("end", 0),
                "duration": ending.get("end", 0) - hook.get("start", 0),
                "hook_text": hook.get("text", ""),
                "ending_text": ending.get("text", ""),
                "body_text": body.get("text", ""),
            })

        output_data = CandidatesData(
            candidates=candidates, candidate_count=len(candidates),
            strategies_used=["story"],
        )
        return create_artifact(data=output_data, stage=ArtifactStage.STORY, parent=graph_artifact)


class HookStrategy(ClipStrategy):
    def strategy_id(self) -> str:
        return "hook"

    async def generate(self, context: PipelineContext) -> Artifact[CandidatesData]:
        graph_artifact = context.get("graph")
        graph = graph_artifact.data if graph_artifact else None
        candidates = []
        events = graph.nodes if graph else []

        for event in events:
            text = event.get("text", "").lower()
            if "?" in text or any(w in text for w in ["secret", "truth", "why", "how"]):
                candidates.append({
                    "id": f"hook_{event.get('id')}", "strategy": "hook",
                    "event_ids": [event.get("id")],
                    "start": event.get("start", 0), "end": event.get("end", 0),
                    "duration": event.get("end", 0) - event.get("start", 0),
                    "hook_text": event.get("text", ""),
                    "ending_text": "", "body_text": "",
                })

        output_data = CandidatesData(
            candidates=candidates, candidate_count=len(candidates),
            strategies_used=["hook"],
        )
        return create_artifact(data=output_data, stage=ArtifactStage.HOOK, parent=graph_artifact)


class RevealStrategy(ClipStrategy):
    def strategy_id(self) -> str:
        return "reveal"

    async def generate(self, context: PipelineContext) -> Artifact[CandidatesData]:
        output_data = CandidatesData(candidates=[], candidate_count=0, strategies_used=["reveal"])
        return create_artifact(data=output_data, stage=ArtifactStage.REVEAL)


class ReactionStrategy(ClipStrategy):
    def strategy_id(self) -> str:
        return "reaction"

    async def generate(self, context: PipelineContext) -> Artifact[CandidatesData]:
        output_data = CandidatesData(candidates=[], candidate_count=0, strategies_used=["reaction"])
        return create_artifact(data=output_data, stage=ArtifactStage.REACTION)


class OpinionStrategy(ClipStrategy):
    def strategy_id(self) -> str:
        return "opinion"

    async def generate(self, context: PipelineContext) -> Artifact[CandidatesData]:
        output_data = CandidatesData(candidates=[], candidate_count=0, strategies_used=["opinion"])
        return create_artifact(data=output_data, stage=ArtifactStage.OPINION)
