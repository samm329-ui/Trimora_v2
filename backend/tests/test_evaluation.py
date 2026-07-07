# backend/tests/test_evaluation.py

import asyncio
import time
import tempfile
import pytest
from pathlib import Path
from backend.core.artifact import Artifact
from backend.core.context import ExecutionContext
from backend.models.data import PortfolioData
from backend.evaluation.layer import EvaluationLayer
from backend.models.evaluation import GroundTruth, EvaluationLifecycle


@pytest.mark.asyncio
async def test_evaluation_creates_records():
    with tempfile.TemporaryDirectory() as d:
        layer = EvaluationLayer(Path(d))
        ctx = ExecutionContext(job_id='eval-001')
        port = PortfolioData(portfolio={'clips': [
            {'id': 'clip1', 'rank': 1, 'overall_score': 0.9, 'objective_scores': {'hook': 0.8}},
            {'id': 'clip2', 'rank': 2, 'overall_score': 0.7, 'objective_scores': {'hook': 0.6}},
        ]})
        art = Artifact(artifact_id='p1', version=1, created_at=time.time(), data=port)
        result = await layer.execute(ctx, art)
        assert len(result['records']) == 2
        assert result['records'][0]['lifecycle'] == 'generated'
        assert result['records'][0]['overall_score'] == 0.9


@pytest.mark.asyncio
async def test_ground_truth_updates_lifecycle():
    with tempfile.TemporaryDirectory() as d:
        layer = EvaluationLayer(Path(d))
        ctx = ExecutionContext(job_id='eval-002')
        port = PortfolioData(portfolio={'clips': [
            {'id': 'clip1', 'rank': 1, 'overall_score': 0.9, 'objective_scores': {}},
        ]})
        art = Artifact(artifact_id='p1', version=1, created_at=time.time(), data=port)
        await layer.execute(ctx, art)

        gt = GroundTruth(generated_clip_id='clip1', creator_rating=4.5, watch_time=120.0)
        layer.record_ground_truth('eval_clip1', gt)

        loaded = layer._load_record('eval_clip1')
        assert loaded.lifecycle == EvaluationLifecycle.EDITED
        assert loaded.ground_truth.creator_rating == 4.5
        assert loaded.ground_truth.watch_time == 120.0


@pytest.mark.asyncio
async def test_empty_portfolio():
    with tempfile.TemporaryDirectory() as d:
        layer = EvaluationLayer(Path(d))
        ctx = ExecutionContext(job_id='eval-003')
        port = PortfolioData(portfolio={'clips': []})
        art = Artifact(artifact_id='p1', version=1, created_at=time.time(), data=port)
        result = await layer.execute(ctx, art)
        assert len(result['records']) == 0


@pytest.mark.asyncio
async def test_record_files_created():
    with tempfile.TemporaryDirectory() as d:
        layer = EvaluationLayer(Path(d))
        ctx = ExecutionContext(job_id='eval-004')
        port = PortfolioData(portfolio={'clips': [
            {'id': 'clip1', 'rank': 1, 'overall_score': 0.9, 'objective_scores': {}},
        ]})
        art = Artifact(artifact_id='p1', version=1, created_at=time.time(), data=port)
        await layer.execute(ctx, art)
        assert (Path(d) / 'eval_clip1.json').exists()
