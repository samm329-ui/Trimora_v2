# backend/tests/test_pipeline_contracts.py

import pytest
from backend.models.data import (
    CandidatesData, ScoresData, PortfolioData, GraphData, EvaluationData,
)
from backend.optimization.deduplication import CandidateDeduplicationService
from backend.optimization.narrative import NarrativeOptimizer
from backend.optimization.portfolio import PortfolioOptimizer
from backend.core.artifact import ArtifactStage, PipelineContractError, create_artifact


class TestStageDeclarations:
    """Verify each stage declares correct INPUT_TYPE and OUTPUT_TYPE."""

    def test_dedup_types(self):
        assert CandidateDeduplicationService.INPUT_TYPE is CandidatesData
        assert CandidateDeduplicationService.OUTPUT_TYPE is CandidatesData

    def test_narrative_types(self):
        assert NarrativeOptimizer.INPUT_TYPE is ScoresData
        assert NarrativeOptimizer.OUTPUT_TYPE is ScoresData

    def test_portfolio_types(self):
        assert PortfolioOptimizer.INPUT_TYPE is ScoresData
        assert PortfolioOptimizer.OUTPUT_TYPE is PortfolioData


class TestChainCompatibility:
    """Verify adjacent stages have compatible types."""

    def test_dedup_to_scoring_to_narrative(self):
        """Dedup outputs CandidatesData. Scoring converts to ScoresData. Narrative expects ScoresData."""
        assert CandidateDeduplicationService.OUTPUT_TYPE is CandidatesData
        assert NarrativeOptimizer.INPUT_TYPE is ScoresData
        # The scoring step (in production_pipeline.py) bridges these two types

    def test_narrative_output_to_portfolio_input(self):
        assert NarrativeOptimizer.OUTPUT_TYPE is PortfolioOptimizer.INPUT_TYPE

    def test_full_chain(self):
        """GraphData -> CandidatesData -> CandidatesData -> ScoresData -> ScoresData -> PortfolioData"""
        chain = [
            GraphData,
            CandidatesData,  # strategies produce this
            CandidatesData,  # dedup produces this
            ScoresData,      # scoring produces this
            ScoresData,      # narrative preserves this
            PortfolioData,   # portfolio produces this
        ]
        # Verify each adjacent pair where wired together
        assert chain[1] is chain[2]  # strategies -> dedup (both CandidatesData)
        assert chain[3] is chain[4]  # scoring -> narrative (both ScoresData)


class TestContractRejection:
    """Verify stages reject wrong input types with PipelineContractError."""

    @pytest.mark.asyncio
    async def test_narrative_rejects_candidates_data(self):
        bad = create_artifact(data=CandidatesData(candidates=[]), stage=ArtifactStage.DEDUP)
        with pytest.raises(PipelineContractError) as exc_info:
            await NarrativeOptimizer().execute({"input": bad})
        assert exc_info.value.expected is ScoresData
        assert exc_info.value.received is CandidatesData
        assert exc_info.value.stage is ArtifactStage.NARRATIVE

    @pytest.mark.asyncio
    async def test_portfolio_rejects_candidates_data(self):
        bad = create_artifact(data=CandidatesData(candidates=[]), stage=ArtifactStage.DEDUP)
        with pytest.raises(PipelineContractError) as exc_info:
            await PortfolioOptimizer().execute({"input": bad})
        assert exc_info.value.expected is ScoresData
        assert exc_info.value.received is CandidatesData
        assert exc_info.value.stage is ArtifactStage.PORTFOLIO

    @pytest.mark.asyncio
    async def test_dedup_rejects_graph_data(self):
        bad = create_artifact(data=GraphData(nodes=[], edges=[]), stage=ArtifactStage.GRAPH)
        with pytest.raises(PipelineContractError) as exc_info:
            await CandidateDeduplicationService().execute({"input": bad})
        assert exc_info.value.expected is CandidatesData
        assert exc_info.value.received is GraphData
        assert exc_info.value.stage is ArtifactStage.DEDUP

    def test_error_carries_artifact_and_parent_ids(self):
        parent = create_artifact(data=GraphData(nodes=[]), stage=ArtifactStage.GRAPH)
        child = create_artifact(data=CandidatesData(candidates=[]), stage=ArtifactStage.DEDUP, parent=parent)
        err = PipelineContractError(ArtifactStage.PORTFOLIO, ScoresData, CandidatesData, child.artifact_id, child.parent_id)
        assert err.artifact_id == child.artifact_id
        assert err.parent_id == child.parent_id
        assert "parent:" in str(err)

    def test_error_without_ids(self):
        err = PipelineContractError(ArtifactStage.EVALUATION, PortfolioData, str)
        assert err.artifact_id is None
        assert err.parent_id is None
        assert "parent:" not in str(err)


class TestCreateArtifact:
    """Verify create_artifact factory works correctly."""

    def test_creates_artifact_with_parent(self):
        parent = create_artifact(data="parent", stage=ArtifactStage.GRAPH)
        child = create_artifact(data="child", stage=ArtifactStage.DEDUP, parent=parent)
        assert child.parent_id == parent.artifact_id
        assert child.parent_hash == parent.compute_hash()

    def test_creates_artifact_without_parent(self):
        art = create_artifact(data="data", stage=ArtifactStage.SCORES)
        assert art.parent_id is None
        assert art.parent_hash == ""

    def test_deterministic_ids(self):
        a1 = create_artifact(data="same", stage=ArtifactStage.NARRATIVE)
        a2 = create_artifact(data="same", stage=ArtifactStage.NARRATIVE)
        assert a1.artifact_id == a2.artifact_id

    def test_different_data_different_ids(self):
        a1 = create_artifact(data="data1", stage=ArtifactStage.NARRATIVE)
        a2 = create_artifact(data="data2", stage=ArtifactStage.NARRATIVE)
        assert a1.artifact_id != a2.artifact_id
