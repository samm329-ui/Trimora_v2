from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path
from time import perf_counter

from backend.config.settings import settings
from backend.models.clip import ClipCandidate
from backend.models.job import JobRecord, JobStatus
from backend.models.segment import AtomicSegment
from backend.models.transcript import TranscriptChunk
from backend.pipelines.analytics_pipeline import AnalyticsPipeline
from backend.pipelines.event_bus import EventBus, PipelineEvent
from backend.pipelines.learning_pipeline import LearningPipeline
from backend.services.audio_service import AudioService
from backend.services.feature_service import FeatureService
from backend.services.graph_service import GraphService
from backend.services.preview_service import PreviewService
from backend.ranking import RankingEngine, Candidate, RankingResult
from backend.services.embedding_service import EmbeddingService
from backend.services.rendering_service import RenderingService
from backend.services.scoring_service import ScoringService
from backend.services.segmentation_service import SegmentationService
from backend.services.transcription_service import TranscriptionService
from backend.storage.file_store import FileStore
from backend.storage.job_store import JobStore
from backend.utils.text_utils import split_sentences
from backend.workers.scheduler import Scheduler


class ProductionPipeline:
    def __init__(self, job_store: JobStore):
        self.job_store = job_store
        self.audio_service = AudioService()
        self.transcription_service = TranscriptionService()
        self.segmentation_service = SegmentationService()
        self.feature_service = FeatureService()
        self.graph_service = GraphService()
        self.scoring_service = ScoringService()
        self.preview_service = PreviewService()
        self.rendering_service = RenderingService()
        self.learning_pipeline = LearningPipeline(FileStore(job_store.root))
        self.analytics_pipeline = AnalyticsPipeline()
        self.event_bus = EventBus()
        self.embedding_service = EmbeddingService()
        self.ranker = RankingEngine(embedder=self.embedding_service)
        self.scheduler = Scheduler(settings.max_transcription_workers)

    async def _publish_event(self, job_id: str, name: str, payload: dict) -> None:
        await self.event_bus.publish(PipelineEvent(job_id=job_id, name=name, payload=payload))

    def _check_cancelled(self, job_id: str) -> JobRecord | None:
        job = self.job_store.load_job(job_id)
        if job.cancelled:
            return self.job_store.set_status(job_id, JobStatus.cancelled, 0.0)
        return None

    async def run(self, job_id: str) -> JobRecord:
        started = perf_counter()
        job = self.job_store.load_job(job_id)
        if job.cancelled:
            return self.job_store.set_status(job_id, JobStatus.cancelled, 0.0)

        if not self.audio_service.check_ffmpeg_available():
            return self.job_store.set_status(
                job_id, JobStatus.failed, 0.0,
                error="ffmpeg/ffprobe not found. Install ffmpeg and ensure it is in PATH.",
            )

        workdir = Path(job.workdir)
        input_video = workdir / "input" / (job.source_filename or "input.mp4")
        audio_path = workdir / "audio" / "audio.opus"
        chunks_dir = workdir / "audio" / "chunks"

        try:
            self.job_store.set_status(job_id, JobStatus.extracting_audio, 0.05)
            try:
                self.audio_service.extract_audio(input_video, audio_path)
            except RuntimeError as e:
                return self.job_store.set_status(
                    job_id, JobStatus.failed, 0.0,
                    error=str(e),
                )
            duration = self.audio_service.probe_duration(input_video)
            await self._publish_event(job_id, "audio_extracted", {"duration": duration})
            cancelled = self._check_cancelled(job_id)
            if cancelled:
                return cancelled

            self.job_store.set_status(job_id, JobStatus.chunking, 0.1)
            chunk_plan = self.audio_service.plan_chunks(duration, speech_density=0.55)
            chunk_ranges = self._build_ranges(duration, chunk_plan.chunk_seconds, chunk_plan.overlap_seconds)
            await self._publish_event(job_id, "chunk_plan_ready", {"chunks": len(chunk_ranges), "workers": chunk_plan.worker_limit})

            self.job_store.set_status(job_id, JobStatus.transcribing, 0.2)
            pool = self.scheduler.build_pool(chunk_plan.worker_limit)

            async def transcribe_one(item: tuple[int, float, float]) -> TranscriptChunk:
                index, start, end = item
                chunk_id = f"{job_id}_chunk_{index}"
                chunk_path = chunks_dir / f"chunk_{index:03d}.opus"

                await asyncio.to_thread(
                    self.audio_service.split_chunk,
                    audio_path, chunk_path, start, end, settings.chunk_bitrate,
                )

                result = await self.transcription_service.transcribe_chunk(chunk_id, chunk_path, start, end)
                return TranscriptChunk(
                    chunk_id=result.chunk_id,
                    start=result.start,
                    end=result.end,
                    text=result.text,
                    confidence=result.confidence,
                )

            transcript_chunks = await pool.run(chunk_ranges, transcribe_one)
            await self._publish_event(job_id, "transcription_completed", {"chunk_count": len(transcript_chunks)})
            cancelled = self._check_cancelled(job_id)
            if cancelled:
                return cancelled

            self.job_store.set_status(job_id, JobStatus.merging, 0.45)
            merged_text = self._merge_transcripts(transcript_chunks)
            self.job_store.file_store.write_json(
                workdir / "transcript" / "transcript.json",
                {"job_id": job_id, "merged_text": merged_text, "chunks": [c.model_dump(mode="json") for c in transcript_chunks]},
            )
            self.job_store.file_store.write_json(
                workdir / "transcript" / "words.json",
                {"chunks": [c.model_dump(mode="json") for c in transcript_chunks]},
            )

            cancelled = self._check_cancelled(job_id)
            if cancelled:
                return cancelled

            self.job_store.set_status(job_id, JobStatus.segmenting, 0.58)
            segments = self.segmentation_service.build_atomic_segments(transcript_chunks)
            self.job_store.file_store.write_json(
                workdir / "segments" / "atomic_segments.json",
                {"segments": [s.model_dump(mode="json") for s in segments]},
            )
            await self._publish_event(job_id, "segments_built", {"segment_count": len(segments)})

            cancelled = self._check_cancelled(job_id)
            if cancelled:
                return cancelled

            self.job_store.set_status(job_id, JobStatus.analyzing, 0.7)
            features = [self.feature_service.compute_features(segment) for segment in segments]
            self.job_store.file_store.write_json(
                workdir / "features" / "feature_vectors.json",
                {"features": [f.model_dump(mode="json") for f in features]},
            )
            graph = self.graph_service.build_graph(segments, features)
            self.job_store.file_store.write_json(
                workdir / "graph" / "local_graph.json",
                graph.model_dump(mode="json"),
            )
            await self._publish_event(job_id, "features_computed", {"feature_count": len(features)})

            cancelled = self._check_cancelled(job_id)
            if cancelled:
                return cancelled

            self.job_store.set_status(job_id, JobStatus.scoring, 0.8)
            candidates = self.scoring_service.generate_candidates(
                segments=segments,
                features=features,
                top_k=settings.preview_top_k,
                min_score=settings.min_candidate_score,
            )
            self.job_store.file_store.write_json(
                workdir / "clips" / "candidates.json",
                {"candidates": [c.model_dump(mode="json") for c in candidates]},
            )

            ranking_candidates = [
                Candidate(
                    id=c.id,
                    hook_text=c.hook_text,
                    body_text=c.body_text,
                    ending_text=c.ending_text,
                    hook_start=c.hook_start,
                    hook_end=c.hook_end,
                    body_start=c.body_start,
                    body_end=c.body_end,
                    ending_start=c.ending_start,
                    ending_end=c.ending_end,
                    duration=c.duration,
                    raw_score=c.total_score,
                    flow_score=c.flow_score,
                )
                for c in candidates
            ]

            ranking_result = self.ranker.rank(ranking_candidates, job_id=job_id)

            self.job_store.file_store.write_json(
                workdir / "clips" / "ranked_clips.json",
                dataclasses.asdict(ranking_result),
            )
            await self._publish_event(job_id, "candidates_ranked", {"candidate_count": len(candidates)})

            cancelled = self._check_cancelled(job_id)
            if cancelled:
                return cancelled

            ranked_clip_ids = {rc.candidate.id for rc in ranking_result.ranked_clips}
            ranked = [c for c in candidates if c.id in ranked_clip_ids]

            preview_manifest = self.preview_service.build_preview(job_id, ranked, settings.preview_top_k)
            self.job_store.file_store.write_json(
                workdir / "clips" / "preview_manifest.json",
                preview_manifest.model_dump(mode="json"),
            )

            self.job_store.set_status(job_id, JobStatus.preview_ready, 0.9)
            job = self.job_store.update_job(job_id, preview_count=len(preview_manifest.clips))
            await self._publish_event(job_id, "preview_ready", {"preview_count": len(preview_manifest.clips)})

            cancelled = self._check_cancelled(job_id)
            if cancelled:
                return cancelled

            export_path = workdir / "exports" / "reel_001.mp4"
            if preview_manifest.clips:
                self.rendering_service.render_clip(input_video, export_path, preview_manifest.clips[0])
                self.job_store.update_job(job_id, export_count=1)
                self.job_store.set_status(job_id, JobStatus.export_ready, 0.95)
                await self._publish_event(job_id, "export_ready", {"export_path": str(export_path)})

            analytics = self.analytics_pipeline.summarize(
                started_at=started,
                number_of_chunks=len(transcript_chunks),
                number_of_candidates=len(candidates),
                number_of_final_clips=1 if preview_manifest.clips else 0,
                worker_utilization=min(1.0, len(chunk_ranges) / max(chunk_plan.worker_limit, 1)),
            )

            asyncio.create_task(self.learning_pipeline.save_analytics_async(workdir, analytics))
            asyncio.create_task(self.learning_pipeline.save_job_learning_async(
                workdir,
                job_id,
                accepted_ids=[c.id for c in preview_manifest.clips[:3]],
                rejected_ids=[c.id for c in ranked[3:10]],
                notes=["Pipeline completed successfully."],
            ))

            self.job_store.update_job(job_id, stats=analytics.model_dump(mode="json"))
            final_status = JobStatus.complete
            return self.job_store.set_status(job_id, final_status, 1.0)

        except Exception as e:
            return self.job_store.set_status(
                job_id, JobStatus.failed, 0.0,
                error=f"Pipeline failed: {e}",
            )
        finally:
            if not settings.keep_chunks:
                import shutil
                shutil.rmtree(chunks_dir, ignore_errors=True)

    def _merge_transcripts(self, chunks: list[TranscriptChunk]) -> str:
        sentences = []
        seen = set()
        for chunk in chunks:
            for sentence in split_sentences(chunk.text):
                normalized = sentence.strip().lower()
                if normalized not in seen:
                    seen.add(normalized)
                    sentences.append(sentence)
        return " ".join(sentences)

    def _build_ranges(self, duration: float, chunk_seconds: int, overlap_seconds: int):
        duration = max(duration, 1.0)
        ranges = []
        start = 0.0
        idx = 0
        while start < duration:
            end = min(duration, start + chunk_seconds)
            ranges.append((idx, round(start, 3), round(end, 3)))
            if end >= duration:
                break
            start = max(end - overlap_seconds, start + 0.5)
            idx += 1
        return ranges
