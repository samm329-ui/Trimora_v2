# backend/tests/test_integration.py

import asyncio
import time
import tempfile
import pytest
from pathlib import Path
from backend.core.artifact import Artifact
from backend.core.context import ExecutionContext, PipelineContext
from backend.core.dag import DAGExecutor, DAGNode
from backend.core.orchestrator import PipelineOrchestrator, StageDefinition
from backend.models.data import TranscriptData, SignalData, GraphData, CandidatesData, ScoresData, PortfolioData
from backend.models.evaluation import GroundTruth, EvaluationLifecycle
from backend.services.adaptive_windows import AdaptiveWindowSplitter
from backend.services.roles import DynamicRoleClassifier
from backend.strategies.builtin import StoryStrategy, HookStrategy
from backend.objectives.builtin import (
    HookDeliveryObjective, StandaloneObjective, EndingObjective,
    DeadTimeObjective, NarrativeCoherenceObjective, InformationDensityObjective,
    TemporalFlowObjective, EmotionalArcObjective
)
from backend.objectives.registry import ObjectiveRegistry
from backend.optimization.portfolio import PortfolioOptimizer
from backend.optimization.deduplication import CandidateDeduplicationService
from backend.optimization.narrative import NarrativeOptimizer
from backend.evaluation.layer import EvaluationLayer


def make_transcript(segments):
    return TranscriptData(segments=segments, merged_text=' '.join(s.get('text', '') for s in segments),
                          word_count=sum(len(s.get('text', '').split()) for s in segments),
                          duration=segments[-1].get('end', 0) if segments else 0)


@pytest.mark.asyncio
async def test_full_pipeline():
    """End-to-end pipeline: Transcript -> Signals -> Graph -> Strategies -> Objectives -> Portfolio -> Evaluation."""
    segments = [
        {'id': 's1', 'text': 'What is the secret to success?', 'start': 0, 'end': 10},
        {'id': 's2', 'text': 'The body of the content with enough words', 'start': 10, 'end': 25},
        {'id': 's3', 'text': 'The body continues with more info', 'start': 25, 'end': 40},
        {'id': 's4', 'text': 'So follow for more content like this', 'start': 40, 'end': 55},
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        # Step 1: Transcript -> Signals
        transcript_data = make_transcript(segments)
        transcript_art = Artifact(artifact_id='t1', version=1, created_at=time.time(), data=transcript_data)
        signals = await AdaptiveWindowSplitter().execute({'transcript': transcript_art})
        assert signals.data.signal_count > 0
        print('  Step 1: Transcript -> Signals OK')

        # Step 2: Signals -> Graph
        from backend.graph.evidence import EvidenceGraph
        graph = await EvidenceGraph().execute({'signals': signals})
        assert graph.data.node_count > 0
        print('  Step 2: Signals -> Graph OK')

        # Step 3: Graph -> Candidates (via strategies)
        ctx = PipelineContext(graph=graph)
        story_result = await StoryStrategy().generate(ctx)
        hook_result = await HookStrategy().generate(ctx)
        total_candidates = story_result.data.candidate_count + hook_result.data.candidate_count
        assert total_candidates > 0
        print(f'  Step 3: Graph -> {total_candidates} candidates OK')

        # Step 4: Merge candidates
        all_candidates = story_result.data.candidates + hook_result.data.candidates
        merged = CandidatesData(candidates=all_candidates, candidate_count=len(all_candidates),
                               strategies_used=['story', 'hook'])
        merged_art = Artifact(artifact_id='merged', version=1, created_at=time.time(), data=merged)

        # Step 5: Deduplication
        dedup = await CandidateDeduplicationService(threshold=0.5).execute({'candidates': merged_art})
        print(f'  Step 5: Dedup {merged.candidate_count} -> {dedup.data.candidate_count} OK')

        # Step 6: Objectives
        reg = ObjectiveRegistry()
        for obj in [HookDeliveryObjective(), StandaloneObjective(), EndingObjective(),
                    DeadTimeObjective(), NarrativeCoherenceObjective(), InformationDensityObjective(),
                    TemporalFlowObjective(), EmotionalArcObjective()]:
            reg.register(obj)

        scored_candidates = []
        for cand in dedup.data.candidates:
            results = reg.score_all(cand, {})
            overall = sum(r.score for r in results.values()) / len(results)
            scored_candidates.append({**cand, 'overall_score': overall, 'objective_scores': {k: r.score for k, r in results.items()}})

        scores_art = Artifact(artifact_id='scores', version=1, created_at=time.time(),
                              data=ScoresData(scored_candidates=scored_candidates))
        print(f'  Step 6: Scored {len(scored_candidates)} candidates OK')

        # Step 7: Portfolio optimization
        portfolio = await PortfolioOptimizer(top_k=5).execute({'scores': scores_art})
        assert portfolio.data.selected_count > 0
        print(f'  Step 7: Portfolio {portfolio.data.selected_count} clips OK')

        # Step 8: Evaluation
        layer = EvaluationLayer(Path(tmpdir) / 'eval')
        ctx2 = ExecutionContext(job_id='integration-test')
        eval_result = await layer.execute(ctx2, portfolio)
        assert len(eval_result['records']) > 0
        print(f'  Step 8: Evaluation {len(eval_result["records"])} records OK')

        print('  FULL PIPELINE PASSED')


@pytest.mark.asyncio
async def test_pipeline_with_error_handling():
    """Pipeline that hits an error in one stage."""
    async def good_stage(inputs):
        return Artifact(artifact_id='good', version=1, created_at=time.time(), data='ok')

    async def bad_stage(inputs):
        raise ValueError('stage failed')

    dag = DAGExecutor()
    dag.add_node(DAGNode(name='good', stage_fn=good_stage))
    dag.add_node(DAGNode(name='bad', stage_fn=bad_stage, depends_on=['good']))
    result = await dag.execute()
    assert result.nodes_failed == 1
    assert result.nodes_succeeded == 1
    print('  Error handling test PASSED')
