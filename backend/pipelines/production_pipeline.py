from __future__ import annotations

import asyncio
import dataclasses
import logging
from pathlib import Path
from time import perf_counter

logger = logging.getLogger(__name__)

from backend.config.settings import settings
from backend.execution.engine import ExecutionEngine, PipelineExecutor
from backend.execution.models import STAGE_SUMMARY, STAGE_PASS1, STAGE_PASS2, STAGE_BLUEPRINT
from backend.execution.provider_session import ProviderSession
from backend.execution.repository import SegmentRepository
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
from backend.services.llm_provider import create_provider
from backend.services.semantic_service import SemanticService, SemanticEnrichmentError
from backend.services.story_reasoner import StoryReasoner, Pass2Error
from backend.services.story_detector import StoryDetector
from backend.services.story_validator import StoryValidator
from backend.services.coverage_analyzer import CoverageAnalyzer
from backend.services.blueprint_generator import BlueprintGenerator
from backend.services.embedding_clusterer import EmbeddingClusterer
from backend.services.block_synopsis_generator import BlockSynopsisGenerator
from backend.services.priority_ranker import PriorityRanker
from backend.services.transcript_summarizer import TranscriptSummarizer
from backend.models.generation_state import BlueprintGenerationState, PipelineTiming, RepairStats
from backend.storage.file_store import FileStore
from backend.storage.job_store import JobStore
from backend.utils.text_utils import split_sentences
from backend.workers.scheduler import Scheduler


class ProductionPipeline:
    def __init__(self, job_store: JobStore, engine: ExecutionEngine | None = None):
        self.job_store = job_store
        self.engine = engine
        self._executor: PipelineExecutor | None = None
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
        # Semantic enrichment services
        self.llm_provider = create_provider(settings.semantic_provider)
        self.semantic_service = SemanticService(self.llm_provider)
        self.story_reasoner = StoryReasoner(self.llm_provider)
        self.story_detector = StoryDetector()
        self.story_validator = StoryValidator()
        self.coverage_analyzer = CoverageAnalyzer()
        self.blueprint_generator = BlueprintGenerator(self.embedding_service)
        # New embedding-first pipeline services
        self.embedding_clusterer = EmbeddingClusterer(self.embedding_service)
        self.block_synopsis_generator = BlockSynopsisGenerator(self.embedding_service)
        self.priority_ranker = PriorityRanker()
        self.transcript_summarizer = TranscriptSummarizer(self.llm_provider)

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

            # --- Semantic Enrichment Layer (Embedding-First Pipeline) ---
            semantic_dir = workdir / "semantic"
            stories_dir = workdir / "stories"
            semantic_dir.mkdir(exist_ok=True)
            stories_dir.mkdir(exist_ok=True)
            timing = PipelineTiming()
            semantic_start = perf_counter()

            # Step 1: Embedding-First Topic Block Clustering
            self.job_store.set_status(job_id, JobStatus.analyzing, 0.70)
            t0 = perf_counter()
            blocks, _embeddings_data = self.embedding_clusterer.cluster(segments)
            timing.semantic_annotation_ms = (perf_counter() - t0) * 1000
            self.job_store.file_store.write_json(
                semantic_dir / "topic_blocks.json",
                {"blocks": [b.model_dump(mode="json") for b in blocks]},
            )

            # Step 2: Block Synopsis Generation (Deterministic)
            t0 = perf_counter()
            for block in blocks:
                block.synopsis = self.block_synopsis_generator.generate_synopsis(block)
                block.representative_excerpt = self.block_synopsis_generator.find_representative_excerpt(block)
            BlockSynopsisGenerator.save_synopses(blocks, semantic_dir / "block_synopses.json")
            timing.story_reasoning_ms = (perf_counter() - t0) * 1000

            # Step 3: Priority Queue (Scheduling Only — never mutates timeline order)
            priority_queue = self.priority_ranker.rank(blocks)
            self.job_store.file_store.write_json(
                semantic_dir / "priority_queue.json",
                priority_queue.model_dump(mode="json"),
            )

            # Step 4: Structured Summary (Root Semantic Artifact — 1 LLM call)
            self.job_store.set_status(job_id, JobStatus.analyzing, 0.72)
            t0 = perf_counter()

            # Build synopses list for execution layer
            synopses_for_summary = [
                {
                    "synopsis": block.synopsis,
                    "representative_excerpt": block.representative_excerpt,
                }
                for block in blocks
            ]

            # Create repository (read-only, per job)
            repo = SegmentRepository(segments, blocks)

            # Initialize executor if not yet done
            if self._executor is None:
                if self.engine is None:
                    from backend.services.llm_provider import create_provider
                    provider = create_provider(settings.semantic_provider)
                    session = ProviderSession(provider, capacity=5500)
                    self.engine = ExecutionEngine(session, max_concurrent=3)
                    await self.engine.start(num_workers=3)
                self._executor = PipelineExecutor(self.engine)
                self._executor.register_stage(STAGE_SUMMARY)
                self._executor.register_stage(STAGE_PASS1)
                self._executor.register_stage(STAGE_PASS2)
                self._executor.register_stage(STAGE_BLUEPRINT)

            # Submit summary request
            summary_request = self.transcript_summarizer.create_request(
                blocks, synopses_for_summary, job_id,
            )
            self._executor.submit_stage(STAGE_SUMMARY, [summary_request], repo)
            summary_handles = await self._executor.wait_for_stage(STAGE_SUMMARY)
            summary_result = await summary_handles[0].result()
            summary_data = self.transcript_summarizer.parse_result(summary_result)

            self.job_store.file_store.write_json(
                semantic_dir / "summary.json",
                summary_data,
            )
            summary_text = summary_data.get("main_topic", "")
            timing.story_verification_ms = (perf_counter() - t0) * 1000

            # Step 5: Pass 1 — Semantic Annotation (with block boundaries, summary context)
            t0 = perf_counter()
            self.job_store.set_status(job_id, JobStatus.analyzing, 0.72)

            pass1_requests = self.semantic_service.create_requests(
                blocks, segments, summary=summary_text, job_id=job_id,
            )
            self._executor.submit_stage(STAGE_PASS1, pass1_requests, repo)
            pass1_handles = await self._executor.wait_for_stage(STAGE_PASS1)

            all_annotations = []
            all_pass1_raw = []
            for handle in pass1_handles:
                try:
                    result = await handle.result()
                    annotations_batch, _ = self.semantic_service.parse_result(result)
                    all_annotations.extend(annotations_batch)
                    all_pass1_raw.append(result.raw_response)
                except Exception as e:
                    logger.warning("Pass 1 handle failed: %s", e)

            from backend.models.semantic import SegmentAnnotations
            annotations = SegmentAnnotations(
                job_id=job_id,
                annotations=all_annotations,
                relationships=[],
            )
            pass1_raw = {"pass1_raw": all_pass1_raw}
            timing.semantic_annotation_ms = (perf_counter() - t0) * 1000

            self.job_store.file_store.write_json(semantic_dir / "segment_annotations.json", annotations.model_dump(mode="json"))
            self.job_store.file_store.write_json(semantic_dir / "pass1_raw.json", pass1_raw)

            # Update repo with annotations for Pass 2
            repo = SegmentRepository(segments, blocks, annotations=annotations)

            # Step 6: Pass 2 — Story Reasoning (block-based prompts, summary context)
            t0 = perf_counter()
            self.job_store.set_status(job_id, JobStatus.analyzing, 0.74)

            pass2_requests = self.story_reasoner.create_requests(
                blocks, segments, annotations, summary_text, job_id,
            )
            self._executor.submit_stage(STAGE_PASS2, pass2_requests, repo)
            pass2_handles = await self._executor.wait_for_stage(STAGE_PASS2)

            all_boundaries = []
            all_pass2_raw = []
            for handle in pass2_handles:
                try:
                    result = await handle.result()
                    boundaries_batch = self.story_reasoner.parse_result(result)
                    all_boundaries.extend(boundaries_batch)
                    all_pass2_raw.append(result.raw_response)
                except Exception as e:
                    logger.warning("Pass 2 handle failed: %s", e)

            boundaries = all_boundaries
            pass2_raw = {"pass2_raw": all_pass2_raw}
            timing.story_reasoning_ms = (perf_counter() - t0) * 1000

            annotations.llm_story_boundaries = boundaries
            self.job_store.file_store.write_json(semantic_dir / "segment_annotations.json", annotations.model_dump(mode="json"))
            self.job_store.file_store.write_json(semantic_dir / "pass2_raw.json", pass2_raw)

            # Story Candidate Formation
            self.job_store.set_status(job_id, JobStatus.analyzing, 0.75)
            candidates_stories = self.story_detector.form_candidates(segments, annotations)

            # Story Verification
            self.job_store.set_status(job_id, JobStatus.analyzing, 0.76)
            t0 = perf_counter()
            candidates_stories = self.story_detector.verify_candidates(candidates_stories, segments, annotations)
            timing.story_verification_ms = (perf_counter() - t0) * 1000
            self.job_store.file_store.write_json(stories_dir / "story_candidates.json", {"candidates": [c.model_dump(mode="json") for c in candidates_stories]})

            # Story Repair
            self.job_store.set_status(job_id, JobStatus.analyzing, 0.77)
            t0 = perf_counter()
            repaired_stories, rejected_stories, repair_records = self.story_detector.repair_candidates(candidates_stories, segments, annotations)
            timing.story_repair_ms = (perf_counter() - t0) * 1000

            # Story Validation
            self.job_store.set_status(job_id, JobStatus.analyzing, 0.78)
            t0 = perf_counter()
            validated_stories, all_rejected = self.story_validator.validate_stories(repaired_stories, rejected_stories, segments, annotations)
            timing.story_validation_ms = (perf_counter() - t0) * 1000
            self.job_store.file_store.write_json(stories_dir / "validated_stories.json", {
                "stories": [s.model_dump(mode="json") for s in validated_stories],
                "rejected_stories": [s.model_dump(mode="json") for s in all_rejected],
            })

            # Coverage Analysis
            t0 = perf_counter()
            coverage = self.coverage_analyzer.compute_coverage(validated_stories, all_rejected, segments)
            timing.coverage_analysis_ms = (perf_counter() - t0) * 1000
            await self._publish_event(job_id, "coverage_analyzed", {
                "coverage_score": coverage.coverage_score,
                "fully_covered": coverage.fully_covered,
                "partially_covered": coverage.partially_covered,
                "unused": coverage.unused,
                "potential_shorts": coverage.potential_additional_shorts,
            })

            # Blueprint Generation
            self.job_store.set_status(job_id, JobStatus.analyzing, 0.80)
            t0 = perf_counter()
            blueprints, gen_state = self.blueprint_generator.generate_blueprints(validated_stories, all_rejected, segments, annotations)
            timing.blueprint_generation_ms = (perf_counter() - t0) * 1000
            timing.total_semantic_ms = (perf_counter() - semantic_start) * 1000

            # Populate generation state
            gen_state.repair_records = repair_records
            gen_state.repair_stats = RepairStats(
                total_candidates=len(candidates_stories),
                candidates_repaired=len(repaired_stories),
                candidates_rejected=len(rejected_stories),
                repair_success_rate=round(len(repaired_stories) / max(len(candidates_stories), 1), 4),
            )
            gen_state.pipeline_timing = timing

            self.job_store.file_store.write_json(workdir / "clips" / "story_blueprints.json", {"blueprints": [b.model_dump(mode="json") for b in blueprints]})
            self.job_store.file_store.write_json(workdir / "clips" / "generation_state.json", gen_state.model_dump(mode="json"))
            await self._publish_event(job_id, "blueprints_generated", {"blueprint_count": len(blueprints)})

            cancelled = self._check_cancelled(job_id)
            if cancelled:
                return cancelled

            # --- End Semantic Enrichment ---

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
