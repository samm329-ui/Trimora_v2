# backend/tests/test_objectives.py

import pytest
from backend.core.artifact import ObjectiveResult
from backend.objectives.builtin import (
    HookDeliveryObjective, StandaloneObjective, EndingObjective,
    DeadTimeObjective, NarrativeCoherenceObjective, InformationDensityObjective,
    TemporalFlowObjective, EmotionalArcObjective, CreatorFitObjective, VisualQualityObjective
)
from backend.objectives.registry import ObjectiveRegistry


CANDIDATE = {
    'hook_text': 'What is the secret?',
    'body_text': 'This body has enough words to test scoring',
    'ending_text': 'So follow for more content',
    'duration': 30,
    'start': 0,
    'end': 30,
    'event_ids': ['e1', 'e2', 'e3'],
}


def test_hook_delivery():
    r = HookDeliveryObjective().score(CANDIDATE, {})
    assert isinstance(r, ObjectiveResult)
    assert 0 <= r.score <= 1
    assert r.confidence > 0


def test_standalone():
    r = StandaloneObjective().score(CANDIDATE, {})
    assert 0 <= r.score <= 1


def test_ending():
    r = EndingObjective().score(CANDIDATE, {})
    assert 0 <= r.score <= 1


def test_dead_time():
    r = DeadTimeObjective().score(CANDIDATE, {})
    assert 0 <= r.score <= 1


def test_narrative_coherence():
    r = NarrativeCoherenceObjective().score(CANDIDATE, {})
    assert 0 <= r.score <= 1


def test_information_density():
    r = InformationDensityObjective().score(CANDIDATE, {})
    assert 0 <= r.score <= 1


def test_temporal_flow():
    r = TemporalFlowObjective().score(CANDIDATE, {})
    assert 0 <= r.score <= 1


def test_emotional_arc():
    r = EmotionalArcObjective().score(CANDIDATE, {})
    assert 0 <= r.score <= 1


def test_creator_fit_skipped():
    r = CreatorFitObjective().score(CANDIDATE, {})
    assert r.status == "skipped"
    assert "Phase 1" in r.error


def test_visual_quality_skipped():
    r = VisualQualityObjective().score(CANDIDATE, {})
    assert r.status == "skipped"


def test_registry_scores_all():
    reg = ObjectiveRegistry()
    objs = [
        HookDeliveryObjective(), StandaloneObjective(), EndingObjective(),
        DeadTimeObjective(), NarrativeCoherenceObjective(), InformationDensityObjective(),
        TemporalFlowObjective(), EmotionalArcObjective(), CreatorFitObjective(), VisualQualityObjective()
    ]
    for o in objs:
        reg.register(o)
    results = reg.score_all(CANDIDATE, {})
    assert len(results) == 10
    assert all(isinstance(r, ObjectiveResult) for r in results.values())


def test_registry_dependency_order():
    reg = ObjectiveRegistry()

    class DepA:
        def objective_id(self): return "a"
        def metadata(self):
            from backend.objectives.base import ObjectiveMetadata
            return ObjectiveMetadata(priority=1, dependencies=[])
        def score(self, c, ctx): return ObjectiveResult(score=0.9, status="success")

    class DepB:
        def objective_id(self): return "b"
        def metadata(self):
            from backend.objectives.base import ObjectiveMetadata
            return ObjectiveMetadata(priority=2, dependencies=["a"])
        def score(self, c, ctx): return ObjectiveResult(score=0.7, status="success")

    reg.register(DepA())
    reg.register(DepB())
    results = reg.score_all({}, {})
    assert results["a"].score == 0.9
    assert results["b"].score == 0.7
