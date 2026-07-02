from backend.models.segment import AtomicSegment
from backend.models.feature import SegmentFeatures
from backend.models.transcript import TranscriptChunk
from backend.ranking.models import Candidate


def make_transcript_chunks() -> list[TranscriptChunk]:
    return [
        TranscriptChunk(chunk_id="chunk_000", start=0.0, end=15.0, text="What if I told you everything you know about productivity is wrong? Here is the truth. Most people waste hours on tasks that don't matter.", confidence=0.92),
        TranscriptChunk(chunk_id="chunk_001", start=13.0, end=28.0, text="The key insight is that you should focus on deep work. Block out two hours each morning for your most important project.", confidence=0.88),
        TranscriptChunk(chunk_id="chunk_002", start=26.0, end=40.0, text="Distractions are the enemy of progress. Turn off notifications. Close your email. Just focus. So that is why deep work matters. Subscribe for more productivity tips.", confidence=0.85),
    ]


def make_segments() -> list[AtomicSegment]:
    return [
        AtomicSegment(id="seg_h_0", start=0.0, end=3.5, text="What if I told you everything you know about productivity is wrong?", kind="hook", order=0),
        AtomicSegment(id="seg_b_0", start=4.0, end=8.0, text="Here is the truth. Most people waste hours on tasks that don't matter.", kind="body", order=1),
        AtomicSegment(id="seg_b_1", start=13.0, end=18.0, text="The key insight is that you should focus on deep work.", kind="body", order=2),
        AtomicSegment(id="seg_b_2", start=18.5, end=25.0, text="Block out two hours each morning for your most important project.", kind="body", order=3),
        AtomicSegment(id="seg_b_3", start=26.0, end=28.5, text="Distractions are the enemy of progress.", kind="body", order=4),
        AtomicSegment(id="seg_b_4", start=29.0, end=33.0, text="Turn off notifications. Close your email. Just focus.", kind="body", order=5),
        AtomicSegment(id="seg_e_0", start=34.0, end=36.0, text="So that is why deep work matters.", kind="ending", order=6),
        AtomicSegment(id="seg_e_1", start=37.0, end=39.0, text="Subscribe for more productivity tips.", kind="ending", order=7),
    ]


def make_features() -> list[SegmentFeatures]:
    return [
        SegmentFeatures(segment_id="seg_h_0", audio_intensity=0.8, text_density=0.75, structure_score=0.9, pattern_score=0.7, total_score=0.7875, audio_energy_source="text_heuristic"),
        SegmentFeatures(segment_id="seg_b_0", audio_intensity=0.6, text_density=0.7, structure_score=0.5, pattern_score=0.65, total_score=0.6125, audio_energy_source="text_heuristic"),
        SegmentFeatures(segment_id="seg_b_1", audio_intensity=0.7, text_density=0.8, structure_score=0.7, pattern_score=0.6, total_score=0.7, audio_energy_source="text_heuristic"),
        SegmentFeatures(segment_id="seg_b_2", audio_intensity=0.65, text_density=0.6, structure_score=0.5, pattern_score=0.55, total_score=0.575, audio_energy_source="text_heuristic"),
        SegmentFeatures(segment_id="seg_b_3", audio_intensity=0.75, text_density=0.85, structure_score=0.5, pattern_score=0.75, total_score=0.7125, audio_energy_source="text_heuristic"),
        SegmentFeatures(segment_id="seg_b_4", audio_intensity=0.7, text_density=0.65, structure_score=0.5, pattern_score=0.6, total_score=0.6125, audio_energy_source="text_heuristic"),
        SegmentFeatures(segment_id="seg_e_0", audio_intensity=0.6, text_density=0.5, structure_score=0.85, pattern_score=0.5, total_score=0.6125, audio_energy_source="text_heuristic"),
        SegmentFeatures(segment_id="seg_e_1", audio_intensity=0.5, text_density=0.4, structure_score=0.85, pattern_score=0.45, total_score=0.55, audio_energy_source="text_heuristic"),
    ]


def make_ranking_candidates() -> list[Candidate]:
    return [
        Candidate(id="clip_1", hook_text="What if I told you everything you know about productivity is wrong?", body_text="Here is the truth. Most people waste hours on tasks that don't matter.", ending_text="So that is why deep work matters. Subscribe for more productivity tips.", hook_start=0.0, hook_end=3.5, body_start=4.0, body_end=8.0, ending_start=34.0, ending_end=39.0, duration=39.0, raw_score=0.75, flow_score=0.85),
        Candidate(id="clip_2", hook_text="The key insight is that you should focus on deep work.", body_text="Block out two hours each morning for your most important project.", ending_text="Subscribe for more productivity tips.", hook_start=13.0, hook_end=18.0, body_start=18.5, body_end=25.0, ending_start=37.0, ending_end=39.0, duration=26.0, raw_score=0.7, flow_score=0.9),
        Candidate(id="clip_3", hook_text="What if I told you everything you know about productivity is wrong?", body_text="Block out two hours each morning for your most important project.", ending_text="Subscribe for more productivity tips.", hook_start=0.0, hook_end=3.5, body_start=18.5, body_end=25.0, ending_start=37.0, ending_end=39.0, duration=39.0, raw_score=0.72, flow_score=0.65),
        Candidate(id="clip_4", hook_text="Distractions are the enemy of progress.", body_text="Turn off notifications. Close your email. Just focus.", ending_text="So that is why deep work matters.", hook_start=26.0, hook_end=28.5, body_start=29.0, body_end=33.0, ending_start=34.0, ending_end=36.0, duration=10.0, raw_score=0.68, flow_score=0.7),
        Candidate(id="clip_5", hook_text="Here is the truth.", body_text="Most people waste hours on tasks that don't matter.", ending_text="Subscribe for more productivity tips.", hook_start=4.0, hook_end=5.0, body_start=5.5, body_end=8.0, ending_start=37.0, ending_end=39.0, duration=35.0, raw_score=0.55, flow_score=0.6),
    ]
