from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
from pathlib import Path
import time
from time import perf_counter
from dataclasses import dataclass

logger = logging.getLogger(__name__)

from backend.config.settings import settings
from backend.execution.models import STAGE_SUMMARY, STAGE_PASS1, STAGE_PASS2, STAGE_BLUEPRINT
from backend.execution.models import LLMTask, LLMExecutionResult, LLMExecutionHandle, TaskPriority, ExecutionRequest
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
from backend.config.models import ModelConfig
from backend.execution.model_registry import ModelRegistry
from backend.execution.token_budget import TokenBudget
from backend.execution.circuit_breaker import CircuitBreaker
from backend.execution.execution_policy import ExecutionPolicy
from backend.execution.provider_adapter import ProviderAdapter
from backend.execution.scheduler import LLMScheduler
from backend.services.token_counter import TokenCounter
from backend.services.prompt_store import PromptStore
from backend.services.payload_validator import PayloadValidator
from backend.services.payload_splitter import PayloadSplitter
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

# V10.1 Pipeline Core
from backend.core.v101_bridge import (
    segments_to_graph_artifact,
    build_pipeline_context,
    merge_strategy_results,
    objective_results_to_scores,
)
from backend.models.data import CandidatesData
from backend.strategies.builtin import StoryStrategy, HookStrategy, RevealStrategy, ReactionStrategy, OpinionStrategy
from backend.optimization.deduplication import CandidateDeduplicationService
from backend.objectives.registry import ObjectiveRegistry
from backend.objectives.builtin import (
    HookDeliveryObjective, StandaloneObjective, EndingObjective, DeadTimeObjective,
    NarrativeCoherenceObjective, InformationDensityObjective, TemporalFlowObjective,
    EmotionalArcObjective, CreatorFitObjective, VisualQualityObjective,
)
from backend.optimization.narrative import NarrativeOptimizer
from backend.optimization.portfolio import PortfolioOptimizer
from backend.evaluation.layer import EvaluationLayer
from backend.services.snapshots import PipelineSnapshotService, SnapshotV1


@dataclass
class ChunkPerformance:
    """Telemetry for a single chunk's transcription performance."""
    chunk_id: str
    audio_duration_s: float
    split_ms: float
    inference_ms: float
    assembly_ms: float
    total_ms: float
    rtf: float


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
        # V10.1 Pipeline Core
        self.strategies = [StoryStrategy(), HookStrategy(), RevealStrategy(), ReactionStrategy(), OpinionStrategy()]
        self.dedup_service = CandidateDeduplicationService(threshold=0.5)
        self.objective_registry = self._build_objective_registry()
        self.narrative_optimizer = NarrativeOptimizer()
        self.portfolio_optimizer = PortfolioOptimizer(top_k=20)
        self.snapshot_service = None  # Initialized per job

        # --- New LLM Scheduler Architecture ---
        self._llm_scheduler: LLMScheduler | None = None
        self._model_registry: ModelRegistry | None = None
        self._prompt_store: PromptStore | None = None

    def _init_llm_scheduler(self) -> LLMScheduler:
        """Initialize the new LLM scheduler architecture (lazy, once per pipeline)."""
        if self._llm_scheduler is not None:
            return self._llm_scheduler

        self._model_registry = ModelRegistry()
        self._model_registry.register_provider("groq", self.llm_provider)
        self._model_registry.register_model(
            ModelConfig(
                name="llama-3.1-8b-instant",
                provider="groq",
                context_window=128000,
                max_input_tokens=126000,
                max_output_tokens=2000,
                rpm_limit=30,
                tpm_limit=6000,
                rpd_limit=14400,
            ),
            provider_name="groq",
        )
        self._model_registry.freeze()

        model_config = self._model_registry.get_config("llama-3.1-8b-instant")
        self._token_counter = TokenCounter(model_config)
        token_budget = TokenBudget(model_config)
        circuit_breaker = CircuitBreaker()

        policy = ExecutionPolicy(
            max_retries=3,
            base_delay=2.0,
            max_delay=30.0,
            request_timeout=90.0,
            circuit_breaker=circuit_breaker,
        )

        self._prompt_store = PromptStore(token_counter=self._token_counter, ttl_seconds=3600.0)
        self._validator = PayloadValidator(self._token_counter)
        self._splitter = PayloadSplitter(self._token_counter, self._prompt_store)

        adapter = ProviderAdapter(
            model_registry=self._model_registry,
            execution_policy=policy,
            token_budget=token_budget,
            prompt_store=self._prompt_store,
        )

        self._llm_scheduler = LLMScheduler(provider_adapter=adapter)
        logger.info("LLM Scheduler architecture initialized")
        return self._llm_scheduler

    def _requests_to_tasks(
        self,
        requests: list[ExecutionRequest],
        repo: SegmentRepository,
        job_id: str,
        task_type: str,
        expected_output_tokens: int,
    ) -> list[LLMTask]:
        """Convert old ExecutionRequests to LLMTasks, resolving prompts into PromptStore."""
        tasks = []
        for req in requests:
            prompt = req.prompt_builder.build(req.prompt_context, repo)
            prompt_tokens = self._token_counter.count(prompt)
            prompt_id = self._prompt_store.store(prompt, job_id, task_type)

            tasks.append(LLMTask(
                task_id=req.request_id,
                task_type=task_type,
                priority=req.priority,
                prompt_id=prompt_id,
                prompt_tokens=prompt_tokens,
                expected_output_tokens=expected_output_tokens,
                model_name="llama-3.1-8b-instant",
                job_id=job_id,
                stage=req.stage.name,
            ))
        return tasks

    async def _submit_and_collect(
        self,
        tasks: list[LLMTask],
    ) -> list[LLMExecutionResult]:
        """Validate, split if needed, submit tasks to LLMScheduler, and collect results."""
        model_config = self._model_registry.get_config("llama-3.1-8b-instant")
        executable_tasks = []

        for task in tasks:
            validation = self._validator.validate(task, model_config)
            if not validation.valid:
                logger.warning("Skipping invalid task %s: %s", task.task_id, validation.reason)
                continue

            split_rec = self._validator.get_split_recommendation(task, model_config)
            if split_rec.needs_split:
                executable_tasks.extend(
                    self._splitter.split(task, split_rec.chunk_size, split_rec.strategy)
                )
            else:
                executable_tasks.append(task)

        if not executable_tasks:
            return []

        handles = [self._llm_scheduler.submit(t) for t in executable_tasks]
        results = await asyncio.gather(*[h.result() for h in handles], return_exceptions=True)

        final_results = []
        for r in results:
            if isinstance(r, Exception):
                logger.error("Task failed with exception: %s", r)
            elif isinstance(r, LLMExecutionResult):
                final_results.append(r)

        return final_results

    async def _publish_event(self, job_id: str, name: str, payload: dict) -> None:
        await self.event_bus.publish(PipelineEvent(job_id=job_id, name=name, payload=payload))

    def _build_objective_registry(self) -> ObjectiveRegistry:
        """Build the V10.1 objective registry with all 10 objectives in dependency order."""
        registry = ObjectiveRegistry()
        registry.register(HookDeliveryObjective())
        registry.register(StandaloneObjective())
        registry.register(EndingObjective())
        registry.register(DeadTimeObjective())
        registry.register(NarrativeCoherenceObjective())
        registry.register(InformationDensityObjective())
        registry.register(TemporalFlowObjective())
        registry.register(EmotionalArcObjective())
        registry.register(CreatorFitObjective())
        registry.register(VisualQualityObjective())
        return registry

    def _get_git_commit(self) -> str:
        """Get current git commit hash."""
        try:
            import subprocess
            result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
            return result.stdout.strip() if result.returncode == 0 else "unknown"
        except Exception:
            return "unknown"

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

            # Log transcription configuration
            if settings.transcription_provider in ("faster-whisper", "whisperx"):
                try:
                    from backend.services.whisper_manager import WhisperManager
                    wm = WhisperManager()
                    whisper_info = wm.info()
                    logger.info(
                        "Transcription config: provider=%s model=%s device=%s compute=%s workers=%d beam_size=%d vad=%s language=%s cpu_cores=%d",
                        whisper_info.provider, whisper_info.model, whisper_info.device,
                        whisper_info.compute_type, whisper_info.workers,
                        settings.whisper_beam_size,
                        "enabled" if settings.whisper_vad_filter else "disabled",
                        settings.whisper_language or "auto",
                        whisper_info.cpu_cores,
                    )
                except Exception as e:
                    logger.warning("Could not get WhisperManager info: %s", e)

            self.job_store.set_status(job_id, JobStatus.chunking, 0.1)
            chunk_plan = self.audio_service.plan_chunks(duration, speech_density=0.55)
            chunk_ranges = self._build_ranges(duration, chunk_plan.chunk_seconds, chunk_plan.overlap_seconds)
            await self._publish_event(job_id, "chunk_plan_ready", {"chunks": len(chunk_ranges), "workers": chunk_plan.worker_limit})

            self.job_store.set_status(job_id, JobStatus.transcribing, 0.2)
            if settings.transcription_provider in ("faster-whisper", "whisperx"):
                from backend.services.whisper_manager import WhisperManager
                worker_count = WhisperManager().worker_count
                logger.info("Local transcription: %d worker(s)", worker_count)
            else:
                worker_count = chunk_plan.worker_limit
            pool = self.scheduler.build_pool(worker_count)

            chunk_perf_stats: list[ChunkPerformance] = []

            async def transcribe_one(item: tuple[int, float, float]) -> TranscriptChunk:
                index, start, end = item
                chunk_id = f"{job_id}_chunk_{index}"
                chunk_path = chunks_dir / f"chunk_{index:03d}.opus"
                audio_duration = end - start

                # Stage 1: Split audio
                t_split = perf_counter()
                await asyncio.to_thread(
                    self.audio_service.split_chunk,
                    audio_path, chunk_path, start, end, settings.chunk_bitrate,
                )
                split_ms = (perf_counter() - t_split) * 1000

                # Stage 2: Whisper inference
                t_infer = perf_counter()
                result = await self.transcription_service.transcribe_chunk(
                    chunk_id, chunk_path, start, end, job_id=job_id
                )
                infer_ms = (perf_counter() - t_infer) * 1000

                # Stage 3: Transcript assembly
                t_assembly = perf_counter()
                chunk = TranscriptChunk(
                    chunk_id=result.chunk_id,
                    start=result.start,
                    end=result.end,
                    text=result.text,
                    confidence=result.confidence,
                )
                assembly_ms = (perf_counter() - t_assembly) * 1000

                # Compute RTF
                total_ms = split_ms + infer_ms + assembly_ms
                rtf = total_ms / 1000 / audio_duration if audio_duration > 0 else 0.0

                perf_stat = ChunkPerformance(
                    chunk_id=chunk_id,
                    audio_duration_s=audio_duration,
                    split_ms=split_ms,
                    inference_ms=infer_ms,
                    assembly_ms=assembly_ms,
                    total_ms=total_ms,
                    rtf=rtf,
                )
                chunk_perf_stats.append(perf_stat)

                logger.info(
                    "Chunk %s [%.1fs]: split=%.0fms infer=%.0fms assembly=%.0fms total=%.0fms RTF=%.2f",
                    chunk_id, audio_duration, split_ms, infer_ms, assembly_ms, total_ms, rtf
                )
                return chunk

            transcript_chunks = await pool.run(chunk_ranges, transcribe_one)

            # Log RTF summary
            if chunk_perf_stats:
                rtf_values = [s.rtf for s in chunk_perf_stats]
                avg_rtf = sum(rtf_values) / len(rtf_values)
                peak_rtf = max(rtf_values)
                avg_duration = sum(s.audio_duration_s for s in chunk_perf_stats) / len(chunk_perf_stats)
                total_infer_ms = sum(s.inference_ms for s in chunk_perf_stats)
                total_audio_s = sum(s.audio_duration_s for s in chunk_perf_stats)

                logger.info(
                    "Transcription summary: chunks=%d avg_rtf=%.2f peak_rtf=%.2f avg_chunk_duration=%.1fs total_inference=%.1fs total_audio=%.1fs",
                    len(chunk_perf_stats), avg_rtf, peak_rtf, avg_duration,
                    total_infer_ms / 1000, total_audio_s,
                )

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

            # Initialize LLM scheduler (new architecture)
            llm_scheduler = self._init_llm_scheduler()
            await llm_scheduler.start(num_workers=1)

            try:
                # Submit summary request via new scheduler
                summary_request = self.transcript_summarizer.create_request(
                    blocks, synopses_for_summary, job_id,
                )
                summary_tasks = self._requests_to_tasks(
                    [summary_request], repo, job_id, "summary", 500,
                )
                summary_results = await self._submit_and_collect(summary_tasks)

                if summary_results:
                    # Wrap LLMExecutionResult as compatible object for parse_result
                    raw_response = summary_results[0].data
                    summary_data = self.transcript_summarizer.parse_result(
                        type("Result", (), {"raw_response": raw_response})()
                    )
                else:
                    summary_data = {}

                self.job_store.file_store.write_json(
                    semantic_dir / "summary.json",
                    summary_data,
                )
                summary_text = summary_data.get("main_topic", "")
                timing.story_verification_ms = (perf_counter() - t0) * 1000

                # Step 5: Pass 1 — Semantic Annotation
                t0 = perf_counter()
                self.job_store.set_status(job_id, JobStatus.analyzing, 0.72)

                pass1_requests = self.semantic_service.create_requests(
                    blocks, segments, summary=summary_text, job_id=job_id,
                )
                pass1_tasks = self._requests_to_tasks(
                    pass1_requests, repo, job_id, "annotation", 800,
                )
                pass1_results = await self._submit_and_collect(pass1_tasks)

                all_annotations = []
                all_pass1_raw = []
                for result in pass1_results:
                    try:
                        compatible = type("Result", (), {"raw_response": result.data})()
                        annotations_batch, _ = self.semantic_service.parse_result(compatible)
                        all_annotations.extend(annotations_batch)
                        all_pass1_raw.append(result.data)
                    except Exception as e:
                        logger.warning("Pass 1 result parse failed: %s", e)

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

                # Step 6: Pass 2 — Story Reasoning
                t0 = perf_counter()
                self.job_store.set_status(job_id, JobStatus.analyzing, 0.74)

                pass2_requests = self.story_reasoner.create_requests(
                    blocks, segments, annotations, summary_text, job_id,
                )
                pass2_tasks = self._requests_to_tasks(
                    pass2_requests, repo, job_id, "reasoning", 600,
                )
                pass2_results = await self._submit_and_collect(pass2_tasks)

                all_boundaries = []
                all_pass2_raw = []
                for result in pass2_results:
                    try:
                        compatible = type("Result", (), {"raw_response": result.data})()
                        boundaries_batch = self.story_reasoner.parse_result(compatible)
                        all_boundaries.extend(boundaries_batch)
                        all_pass2_raw.append(result.data)
                    except Exception as e:
                        logger.warning("Pass 2 result parse failed: %s", e)

                boundaries = all_boundaries
                pass2_raw = {"pass2_raw": all_pass2_raw}
                timing.story_reasoning_ms = (perf_counter() - t0) * 1000

                annotations.llm_story_boundaries = boundaries
                self.job_store.file_store.write_json(semantic_dir / "segment_annotations.json", annotations.model_dump(mode="json"))
                self.job_store.file_store.write_json(semantic_dir / "pass2_raw.json", pass2_raw)

                # Cleanup expired prompts
                self._prompt_store.cleanup_expired()
                logger.info("LLM Scheduler metrics: %s", llm_scheduler.metrics.to_dict())

            finally:
                await llm_scheduler.stop()

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

            # --- V10.1 Pipeline Core Integration ---
            v101_start = perf_counter()
            self.job_store.set_status(job_id, JobStatus.analyzing, 0.81)

            # Initialize snapshot service for this job
            self.snapshot_service = PipelineSnapshotService(workdir)

            # Step V1: Convert segments to graph artifact for strategies
            graph_artifact = segments_to_graph_artifact(segments)
            pipeline_context = build_pipeline_context(segments, graph_artifact)

            # Step V2: Run all 5 clip strategies
            strategy_results = []
            for strategy in self.strategies:
                try:
                    result = await strategy.generate(pipeline_context)
                    strategy_results.append(result)
                except Exception as e:
                    logger.warning("Strategy %s failed: %s", strategy.strategy_id(), e)

            # Step V3: Merge strategy candidates
            all_candidates, strategies_used = merge_strategy_results(strategy_results)
            await self._publish_event(job_id, "v101_strategies_done", {
                "candidate_count": len(all_candidates),
                "strategies": strategies_used,
            })

            # Step V4: Deduplicate candidates
            if all_candidates:
                dedup_artifact = await self.dedup_service.execute({"candidates": graph_artifact})
                all_candidates = dedup_artifact.data.candidates if dedup_artifact and dedup_artifact.data else all_candidates

            # Step V5: Score candidates with V10.1 objectives (DAG order)
            scored_candidates = []
            for candidate in all_candidates:
                obj_results = self.objective_registry.score_all(candidate, {"job_id": job_id})
                score_summary = objective_results_to_scores(obj_results, candidate)
                scored_candidates.append({
                    **candidate,
                    "objective_scores": score_summary["objective_scores"],
                    "v101_score": score_summary["overall_score"],
                })

            # Step V6: Narrative optimization (sort by start time)
            scores_artifact = CandidatesData(
                candidates=scored_candidates,
                candidate_count=len(scored_candidates),
                strategies_used=strategies_used,
            )
            from backend.core.artifact import Artifact as V101Artifact, generate_deterministic_id, compute_output_hash
            scores_v101_artifact = V101Artifact(
                artifact_id=generate_deterministic_id(graph_artifact.compute_hash(), "scores", 1, output_hash=compute_output_hash(scores_artifact)),
                version=1, created_at=time.time(),
                data=scores_artifact,
            )
            narrative_result = await self.narrative_optimizer.execute({"scores": scores_v101_artifact})

            # Step V7: Portfolio optimization (MMR + diversity)
            portfolio_result = await self.portfolio_optimizer.execute({"narrative": narrative_result})

            # Step V8: Save evaluation records
            eval_dir = workdir / "evaluations"
            eval_dir.mkdir(exist_ok=True)
            eval_layer = EvaluationLayer(eval_dir)
            eval_context = type('Context', (), {
                "job_id": job_id,
                "config": type('Config', (), {"to_dict": lambda self: {"pipeline_version": "v10.1.0"}})()
            })()
            if portfolio_result and portfolio_result.data:
                eval_result = await eval_layer.execute(eval_context, portfolio_result)
                await self._publish_event(job_id, "v101_evaluation_done", {
                    "record_count": len(eval_result.get("records", [])),
                })

            # Step V9: Save snapshot
            snapshot = SnapshotV1(
                stage="v101_complete",
                timestamp=time.time(),
                job_id=job_id,
                data={"candidate_count": len(scored_candidates), "strategies_used": strategies_used},
                config_snapshot={"pipeline_version": "v10.1.0"},
                git_commit=self._get_git_commit(),
                feature_flags={"v101_enabled": True},
            )
            self.snapshot_service.save_snapshot(snapshot)

            v101_ms = (perf_counter() - v101_start) * 1000
            await self._publish_event(job_id, "v101_complete", {"v101_ms": v101_ms})
            logger.info("V10.1 pipeline stages completed in %.0fms", v101_ms)

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
            # Clear cached language for this job
            if settings.transcription_provider in ("faster-whisper", "whisperx"):
                try:
                    from backend.services.whisper_manager import WhisperManager
                    WhisperManager().clear_job_language(job_id)
                except Exception:
                    pass

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
