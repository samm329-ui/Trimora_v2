from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

dotenv_path = Path(__file__).resolve().parents[2] / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)


@dataclass
class Settings:
    root_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])
    storage_root: Path = field(default_factory=lambda: Path("./storage"))
    jobs_root: Path = field(default_factory=lambda: Path("./storage/jobs"))
    max_transcription_workers: int = 5
    max_feature_workers: int = 15
    max_clip_workers: int = 8
    min_chunk_seconds: int = 30
    max_chunk_seconds: int = 120
    overlap_seconds: int = 2
    chunk_bitrate: str = "64k"
    keep_chunks: bool = True
    retry_count: int = 3
    transcription_provider: str = "stub"
    groq_api_key: str = ""
    groq_api_keys: list[str] = field(default_factory=list)
    gemini_api_key: str = ""
    transcription_timeout_seconds: int = 600
    export_timeout_seconds: int = 600
    min_segment_seconds: float = 1.2
    min_candidate_score: float = 0.35
    preview_top_k: int = 20
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    # Semantic enrichment
    semantic_provider: str = "auto"
    semantic_batch_size: int = 10
    semantic_context_overlap: int = 2
    semantic_batch_delay_seconds: float = 0.0
    semantic_min_confidence: float = 0.3
    story_min_quality: float = 0.3
    story_min_segments: int = 3
    story_repair_max_extensions: int = 3
    duplicate_similarity_threshold: float = 0.90
    duplicate_segment_overlap: float = 0.95
    blueprint_short_max: float = 90.0
    segment_max_usage: int = 3
    # Embedding clustering
    embedding_min_window: int = 3
    embedding_target_window: int = 5
    embedding_max_window: int = 7
    embedding_max_duration: float = 60.0
    embedding_max_tokens: int = 2000
    embedding_smoothing_window: int = 3
    embedding_threshold_std: float = 1.5
    embedding_z_score_max_std: float = 3.0

    @classmethod
    def load(cls) -> "Settings":
        base = cls()
        cfg = Path(__file__).with_name("runtime.yaml")
        data: dict[str, Any] = {}
        if cfg.exists():
            data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}

        workers = data.get("workers", {})
        chunking = data.get("chunking", {})
        storage = data.get("storage", {})
        job = data.get("job", {})
        thresholds = data.get("thresholds", {})
        semantic = data.get("semantic", {})
        embedding = data.get("embedding", {})

        base.storage_root = Path(storage.get("root", base.storage_root))
        base.jobs_root = Path(storage.get("jobs_root", base.jobs_root))
        base.max_transcription_workers = int(workers.get("max_transcription_workers", base.max_transcription_workers))
        base.max_feature_workers = int(workers.get("max_feature_workers", base.max_feature_workers))
        base.max_clip_workers = int(workers.get("max_clip_workers", base.max_clip_workers))
        base.min_chunk_seconds = int(chunking.get("min_seconds", base.min_chunk_seconds))
        base.max_chunk_seconds = int(chunking.get("max_seconds", base.max_chunk_seconds))
        base.overlap_seconds = int(chunking.get("overlap_seconds", base.overlap_seconds))
        base.chunk_bitrate = str(chunking.get("bitrate", base.chunk_bitrate))
        base.keep_chunks = bool(chunking.get("keep_chunks", base.keep_chunks))
        base.retry_count = int(job.get("retry_count", base.retry_count))
        base.transcription_provider = str(job.get("transcription_provider", base.transcription_provider))
        base.transcription_timeout_seconds = int(job.get("transcription_timeout_seconds", base.transcription_timeout_seconds))
        base.groq_api_key = str(os.getenv("GROQ_API_KEY", ""))
        base.groq_api_keys = []
        for i in range(1, 10):
            key = os.getenv(f"GROQ_API_KEY_{i}", "")
            if key:
                base.groq_api_keys.append(key)
        base.gemini_api_key = str(os.getenv("GEMINI_API_KEY", ""))
        base.export_timeout_seconds = int(job.get("export_timeout_seconds", base.export_timeout_seconds))
        base.min_segment_seconds = float(thresholds.get("min_segment_seconds", base.min_segment_seconds))
        base.min_candidate_score = float(thresholds.get("min_candidate_score", base.min_candidate_score))
        base.preview_top_k = int(thresholds.get("preview_top_k", base.preview_top_k))

        base.storage_root = Path(os.getenv("TRIMORA_STORAGE_ROOT", str(base.storage_root)))
        base.jobs_root = Path(os.getenv("TRIMORA_JOBS_ROOT", str(base.jobs_root)))

        # Semantic enrichment settings
        base.semantic_provider = str(semantic.get("provider", os.getenv("SEMANTIC_PROVIDER", base.semantic_provider)))
        base.semantic_batch_size = int(semantic.get("batch_size", base.semantic_batch_size))
        base.semantic_context_overlap = int(semantic.get("context_overlap", base.semantic_context_overlap))
        base.semantic_min_confidence = float(semantic.get("min_confidence", base.semantic_min_confidence))
        base.story_min_quality = float(semantic.get("story_min_quality", base.story_min_quality))
        base.story_min_segments = int(semantic.get("story_min_segments", base.story_min_segments))
        base.story_repair_max_extensions = int(semantic.get("repair_max_extensions", base.story_repair_max_extensions))
        base.duplicate_similarity_threshold = float(semantic.get("duplicate_similarity_threshold", base.duplicate_similarity_threshold))
        base.duplicate_segment_overlap = float(semantic.get("duplicate_segment_overlap", base.duplicate_segment_overlap))
        base.blueprint_short_max = float(semantic.get("blueprint_short_max", base.blueprint_short_max))
        base.segment_max_usage = int(semantic.get("segment_max_usage", base.segment_max_usage))

        # Embedding clustering settings
        base.embedding_min_window = int(embedding.get("min_window", base.embedding_min_window))
        base.embedding_target_window = int(embedding.get("target_window", base.embedding_target_window))
        base.embedding_max_window = int(embedding.get("max_window", base.embedding_max_window))
        base.embedding_max_duration = float(embedding.get("max_duration", base.embedding_max_duration))
        base.embedding_max_tokens = int(embedding.get("max_tokens", base.embedding_max_tokens))
        base.embedding_smoothing_window = int(embedding.get("smoothing_window", base.embedding_smoothing_window))
        base.embedding_threshold_std = float(embedding.get("threshold_std", base.embedding_threshold_std))
        base.embedding_z_score_max_std = float(embedding.get("z_score_max_std", base.embedding_z_score_max_std))

        return base


settings = Settings.load()
