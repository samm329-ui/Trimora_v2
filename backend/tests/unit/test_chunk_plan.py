from backend.utils.audio_utils import build_chunk_plan


def test_chunk_plan_small():
    plan = build_chunk_plan(120, 0.7)
    assert plan.chunk_seconds >= 20
    assert plan.worker_limit <= 15
