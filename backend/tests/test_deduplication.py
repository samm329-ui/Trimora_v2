# backend/tests/test_deduplication.py

import asyncio
import time
import pytest
from backend.core.artifact import Artifact
from backend.models.data import CandidatesData
from backend.optimization.deduplication import CandidateDeduplicationService, JaccardSimilarity


@pytest.mark.asyncio
async def test_removes_duplicates():
    cands = [
        {'id': 'c1', 'event_ids': ['e1', 'e2', 'e3']},
        {'id': 'c2', 'event_ids': ['e1', 'e2', 'e3']},
        {'id': 'c3', 'event_ids': ['e4', 'e5']},
    ]
    art = Artifact(artifact_id='cd', version=1, created_at=time.time(),
                   data=CandidatesData(candidates=cands, candidate_count=3))
    result = await CandidateDeduplicationService(threshold=0.5).execute({'candidates': art})
    assert result.data.candidate_count == 2
    ids = [c['id'] for c in result.data.candidates]
    assert 'c1' in ids and 'c3' in ids
    assert 'c2' not in ids


@pytest.mark.asyncio
async def test_keeps_unique():
    cands = [
        {'id': 'c1', 'event_ids': ['e1', 'e2']},
        {'id': 'c2', 'event_ids': ['e3', 'e4']},
        {'id': 'c3', 'event_ids': ['e5', 'e6']},
    ]
    art = Artifact(artifact_id='cd', version=1, created_at=time.time(),
                   data=CandidatesData(candidates=cands, candidate_count=3))
    result = await CandidateDeduplicationService(threshold=0.5).execute({'candidates': art})
    assert result.data.candidate_count == 3


@pytest.mark.asyncio
async def test_empty_candidates():
    art = Artifact(artifact_id='cd', version=1, created_at=time.time(),
                   data=CandidatesData(candidates=[], candidate_count=0))
    result = await CandidateDeduplicationService().execute({'candidates': art})
    assert result.data.candidate_count == 0


@pytest.mark.asyncio
async def test_custom_similarity_provider():
    class AlwaysSimilar:
        def compute(self, c1, c2): return 1.0

    cands = [
        {'id': 'c1', 'event_ids': ['e1']},
        {'id': 'c2', 'event_ids': ['e2']},
    ]
    art = Artifact(artifact_id='cd', version=1, created_at=time.time(),
                   data=CandidatesData(candidates=cands, candidate_count=2))
    result = await CandidateDeduplicationService(
        threshold=0.5, similarity_provider=AlwaysSimilar()
    ).execute({'candidates': art})
    assert result.data.candidate_count == 1


def test_jaccard_similarity():
    j = JaccardSimilarity()
    assert j.compute({'event_ids': ['e1', 'e2']}, {'event_ids': ['e1', 'e2']}) == 1.0
    assert j.compute({'event_ids': ['e1']}, {'event_ids': ['e2']}) == 0.0
    assert j.compute({'event_ids': ['e1', 'e2']}, {'event_ids': ['e2', 'e3']}) == 1/3
    assert j.compute({}, {}) == 0.0


@pytest.mark.asyncio
async def test_deduplication_result_metadata():
    cands = [
        {'id': 'c1', 'event_ids': ['e1', 'e2']},
        {'id': 'c2', 'event_ids': ['e1', 'e2']},
    ]
    art = Artifact(artifact_id='cd', version=1, created_at=time.time(),
                   data=CandidatesData(candidates=cands, candidate_count=2))
    result = await CandidateDeduplicationService(threshold=0.5).execute({'candidates': art})
    dr = result.data.deduplication_result
    assert dr['original_count'] == 2
    assert dr['final_count'] == 1
    assert len(dr['removed']) == 1
    assert dr['removed'][0]['candidate_id'] == 'c2'
