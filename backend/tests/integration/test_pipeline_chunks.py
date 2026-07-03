from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.job import JobStatus
from backend.pipelines.production_pipeline import ProductionPipeline
from backend.ranking import RankingResult
from backend.storage.job_store import JobStore


def _make_video_with_audio(path: Path, duration: float = 5.0):
    """Create a minimal video with audio track for pipeline testing."""
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-f", "lavfi", "-i", f"color=c=black:s=320x240:d={duration}",
        "-map", "0:a", "-map", "1:v",
        "-c:a", "libopus", "-c:v", "libx264",
        "-shortest",
        str(path),
    ], check=True, capture_output=True)


@pytest.mark.integration
def test_pipeline_creates_chunks_and_passes_to_transcription():
    """End-to-end: pipeline creates physical chunk files and passes them to transcription.

    Intercepts transcribe_chunk() to validate paths during execution,
    since keep_chunks=False removes them before we can check the filesystem.
    """
    chunk_paths_received = []

    with tempfile.TemporaryDirectory() as tmpdir:
        workdir = Path(tmpdir) / "jobs" / "test-job-001"
        input_dir = workdir / "input"
        input_dir.mkdir(parents=True)

        video_path = input_dir / "test.mp4"
        _make_video_with_audio(video_path, duration=5.0)

        job_store = MagicMock(spec=JobStore)
        job_store.root = Path(tmpdir)
        job_store.file_store = MagicMock()
        job_store.set_status.return_value = MagicMock(status=JobStatus.complete)
        job_store.update_job.return_value = MagicMock(
            job_id="test-job-001",
            preview_count=0,
        )
        job_store.load_job.return_value = MagicMock(
            job_id="test-job-001",
            source_filename="test.mp4",
            workdir=str(workdir),
            cancelled=False,
        )

        pipeline = ProductionPipeline(job_store)

        original_transcribe = pipeline.transcription_service.transcribe_chunk

        async def capturing_transcribe(chunk_id, chunk_path, start, end):
            chunk_paths_received.append((chunk_id, chunk_path, start, end))
            assert chunk_path.exists(), f"Chunk file does not exist: {chunk_path}"
            assert chunk_path.stat().st_size > 0, f"Chunk file is empty: {chunk_path}"
            return await original_transcribe(chunk_id, chunk_path, start, end)

        pipeline.transcription_service.transcribe_chunk = capturing_transcribe

        pipeline.segmentation_service.build_atomic_segments = MagicMock(return_value=[])
        pipeline.feature_service.compute_features = MagicMock(return_value=MagicMock())
        pipeline.graph_service.build_graph = MagicMock(return_value=MagicMock())
        pipeline.scoring_service.generate_candidates = MagicMock(return_value=[])
        pipeline.ranker.rank = MagicMock(return_value=RankingResult(ranked_clips=[]))
        pipeline.preview_service.build_preview = MagicMock(return_value=MagicMock(clips=[]))
        pipeline.rendering_service.render_clip = MagicMock()
        pipeline.learning_pipeline.save_analytics_async = AsyncMock()
        pipeline.learning_pipeline.save_job_learning_async = AsyncMock()

        with patch("backend.pipelines.production_pipeline.settings") as mock_settings:
            mock_settings.max_transcription_workers = 2
            mock_settings.chunk_bitrate = "64k"
            mock_settings.keep_chunks = False
            mock_settings.transcription_provider = "stub"
            mock_settings.preview_top_k = 5
            mock_settings.min_candidate_score = 0.3

            result = asyncio.run(pipeline.run("test-job-001"))

        assert result.status.value == "complete"

        assert len(chunk_paths_received) > 0, "No transcription calls were made"
        paths = [cp for _, cp, _, _ in chunk_paths_received]
        assert len(paths) == len(set(paths)), "Duplicate chunk paths sent to transcription"

        for _, cp, _, _ in chunk_paths_received:
            assert str(cp).endswith(".opus")
            assert "chunk_" in cp.name

        starts = [s for _, _, s, _ in chunk_paths_received]
        ends = [e for _, _, _, e in chunk_paths_received]
        assert starts == sorted(starts), "Chunk start times are not monotonically increasing"
        assert ends[-1] >= 4.0, "Chunks don't cover the full video duration"
