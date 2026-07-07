# backend/tests/test_strategies.py

import asyncio
import time
import pytest
from backend.core.artifact import Artifact
from backend.core.context import PipelineContext
from backend.models.data import GraphData, CandidatesData
from backend.strategies.builtin import StoryStrategy, HookStrategy, RevealStrategy, ReactionStrategy, OpinionStrategy


def make_graph_artifact(nodes):
    return Artifact(artifact_id='g1', version=1, created_at=time.time(), data=GraphData(nodes=nodes))


@pytest.mark.asyncio
async def test_story_strategy_generates_candidates():
    nodes = [
        {'id': 'e1', 'text': 'hook question?', 'start': 0, 'end': 10},
        {'id': 'e2', 'text': 'body content here', 'start': 10, 'end': 20},
        {'id': 'e3', 'text': 'ending so therefore', 'start': 20, 'end': 30},
    ]
    ctx = PipelineContext(graph=make_graph_artifact(nodes))
    result = await StoryStrategy().generate(ctx)
    assert isinstance(result, Artifact)
    assert result.data.candidate_count >= 1
    assert result.data.candidates[0]['strategy'] == 'story'
    assert result.data.candidates[0]['start'] == 0
    assert result.data.candidates[0]['end'] == 30


@pytest.mark.asyncio
async def test_hook_strategy_generates_hooks():
    nodes = [
        {'id': 'e1', 'text': 'What is the secret?', 'start': 0, 'end': 10},
        {'id': 'e2', 'text': 'normal body', 'start': 10, 'end': 20},
        {'id': 'e3', 'text': 'Why does this work?', 'start': 20, 'end': 30},
    ]
    ctx = PipelineContext(graph=make_graph_artifact(nodes))
    result = await HookStrategy().generate(ctx)
    assert result.data.candidate_count == 2
    assert all(c['strategy'] == 'hook' for c in result.data.candidates)


@pytest.mark.asyncio
async def test_empty_graph():
    ctx = PipelineContext(graph=make_graph_artifact([]))
    story = await StoryStrategy().generate(ctx)
    hook = await HookStrategy().generate(ctx)
    assert story.data.candidate_count == 0
    assert hook.data.candidate_count == 0


@pytest.mark.asyncio
async def test_reveal_strategy_empty():
    ctx = PipelineContext()
    result = await RevealStrategy().generate(ctx)
    assert result.data.candidate_count == 0
    assert result.data.strategies_used == ["reveal"]


@pytest.mark.asyncio
async def test_reaction_strategy_empty():
    ctx = PipelineContext()
    result = await ReactionStrategy().generate(ctx)
    assert result.data.candidate_count == 0
    assert result.data.strategies_used == ["reaction"]


@pytest.mark.asyncio
async def test_opinion_strategy_empty():
    ctx = PipelineContext()
    result = await OpinionStrategy().generate(ctx)
    assert result.data.candidate_count == 0
    assert result.data.strategies_used == ["opinion"]


@pytest.mark.asyncio
async def test_deterministic_ids():
    nodes = [{'id': 'e1', 'text': '?', 'start': 0, 'end': 10}]
    ctx = PipelineContext(graph=make_graph_artifact(nodes))
    r1 = await HookStrategy().generate(ctx)
    r2 = await HookStrategy().generate(ctx)
    assert r1.artifact_id == r2.artifact_id
