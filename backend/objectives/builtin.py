# backend/objectives/builtin.py

from backend.objectives.base import Objective, ObjectiveMetadata
from backend.core.artifact import ObjectiveResult


class HookDeliveryObjective(Objective):
    def objective_id(self) -> str:
        return "hook_delivery"

    def metadata(self) -> ObjectiveMetadata:
        return ObjectiveMetadata(priority=1, phase="baseline", expected_latency_ms=5.0,
                                 deterministic=True, cacheable=True, description="Measures hook strength")

    def score(self, candidate: dict, context: dict) -> ObjectiveResult:
        hook_text = candidate.get("hook_text", "").lower()
        score = 0.5
        if "?" in candidate.get("hook_text", ""):
            score += 0.2
        if "you" in hook_text.split():
            score += 0.1
        if any(w in hook_text for w in ["secret", "truth", "why", "how", "never", "always"]):
            score += 0.15
        if len(candidate.get("hook_text", "").split()) <= 10:
            score += 0.1
        return ObjectiveResult(score=min(1.0, score), confidence=0.8, status="success")


class StandaloneObjective(Objective):
    def objective_id(self) -> str:
        return "standalone"

    def metadata(self) -> ObjectiveMetadata:
        return ObjectiveMetadata(priority=2, phase="baseline", expected_latency_ms=5.0,
                                 deterministic=True, cacheable=True, description="Standalone clarity")

    def score(self, candidate: dict, context: dict) -> ObjectiveResult:
        body = candidate.get("body_text", "")
        score = 0.8 if len(body.split()) >= 10 else 0.5
        return ObjectiveResult(score=score, confidence=0.7, status="success")


class EndingObjective(Objective):
    def objective_id(self) -> str:
        return "ending"

    def metadata(self) -> ObjectiveMetadata:
        return ObjectiveMetadata(priority=3, phase="baseline", expected_latency_ms=5.0,
                                 deterministic=True, cacheable=True, description="Ending strength")

    def score(self, candidate: dict, context: dict) -> ObjectiveResult:
        ending = candidate.get("ending_text", "").lower()
        score = 0.85 if any(w in ending for w in ["so", "therefore", "that's", "subscribe", "follow"]) else 0.5
        return ObjectiveResult(score=score, confidence=0.7, status="success")


class DeadTimeObjective(Objective):
    def objective_id(self) -> str:
        return "dead_time"

    def metadata(self) -> ObjectiveMetadata:
        return ObjectiveMetadata(priority=4, phase="baseline", expected_latency_ms=5.0,
                                 deterministic=True, cacheable=True, description="Dead time penalty")

    def score(self, candidate: dict, context: dict) -> ObjectiveResult:
        duration = candidate.get("duration", 0)
        if 15 <= duration <= 45:
            return ObjectiveResult(score=1.0, confidence=0.9, status="success")
        if duration < 15:
            return ObjectiveResult(score=0.5, confidence=0.9, status="success")
        return ObjectiveResult(score=0.7, confidence=0.8, status="success")


class NarrativeCoherenceObjective(Objective):
    def objective_id(self) -> str:
        return "narrative_coherence"

    def metadata(self) -> ObjectiveMetadata:
        return ObjectiveMetadata(priority=5, phase="baseline", expected_latency_ms=10.0,
                                 deterministic=True, cacheable=True, description="Narrative coherence")

    def score(self, candidate: dict, context: dict) -> ObjectiveResult:
        events = candidate.get("event_ids", [])
        score = min(1.0, len(events) / 3.0) if events else 0.3
        return ObjectiveResult(score=score, confidence=0.6, status="success")


class InformationDensityObjective(Objective):
    def objective_id(self) -> str:
        return "information_density"

    def metadata(self) -> ObjectiveMetadata:
        return ObjectiveMetadata(priority=6, phase="baseline", expected_latency_ms=5.0,
                                 deterministic=True, cacheable=True, description="Information density")

    def score(self, candidate: dict, context: dict) -> ObjectiveResult:
        body = candidate.get("body_text", "")
        words = len(body.split())
        duration = max(candidate.get("duration", 1), 0.1)
        wps = words / duration
        score = 0.9 if 2.5 <= wps <= 3.5 else 0.5
        return ObjectiveResult(score=score, confidence=0.8, status="success")


class TemporalFlowObjective(Objective):
    def objective_id(self) -> str:
        return "temporal_flow"

    def metadata(self) -> ObjectiveMetadata:
        return ObjectiveMetadata(priority=7, phase="baseline", expected_latency_ms=5.0,
                                 deterministic=True, cacheable=True, description="Temporal flow")

    def score(self, candidate: dict, context: dict) -> ObjectiveResult:
        duration = candidate.get("end", 0) - candidate.get("start", 0)
        score = 0.9 if 20 <= duration <= 60 else 0.5
        return ObjectiveResult(score=score, confidence=0.8, status="success")


class EmotionalArcObjective(Objective):
    def objective_id(self) -> str:
        return "emotional_arc"

    def metadata(self) -> ObjectiveMetadata:
        return ObjectiveMetadata(priority=8, phase="baseline", expected_latency_ms=5.0,
                                 deterministic=True, cacheable=True, description="Emotional arc")

    def score(self, candidate: dict, context: dict) -> ObjectiveResult:
        return ObjectiveResult(score=0.6, confidence=0.5, status="success")


class CreatorFitObjective(Objective):
    def objective_id(self) -> str:
        return "creator_fit"

    def metadata(self) -> ObjectiveMetadata:
        return ObjectiveMetadata(priority=9, phase="experimental", expected_latency_ms=10.0,
                                 deterministic=True, cacheable=False, description="Creator fit",
                                 minimum_data=100, baseline_only=False)

    def score(self, candidate: dict, context: dict) -> ObjectiveResult:
        return ObjectiveResult(score=0.5, confidence=0.0, status="skipped",
                               error="No creator data in Phase 1")


class VisualQualityObjective(Objective):
    def objective_id(self) -> str:
        return "visual_quality"

    def metadata(self) -> ObjectiveMetadata:
        return ObjectiveMetadata(priority=10, phase="experimental", expected_latency_ms=200.0,
                                 deterministic=False, cacheable=False, description="Visual quality",
                                 minimum_data=1000, baseline_only=False)

    def score(self, candidate: dict, context: dict) -> ObjectiveResult:
        return ObjectiveResult(score=0.5, confidence=0.0, status="skipped",
                               error="No vision model in Phase 1")
