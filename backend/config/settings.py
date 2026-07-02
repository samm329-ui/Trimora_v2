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
    max_transcription_workers: int = 15
    max_feature_workers: int = 15
    max_clip_workers: int = 8
    min_chunk_seconds: int = 30
    max_chunk_seconds: int = 120
    overlap_seconds: int = 2
    retry_count: int = 3
    transcription_provider: str = "stub"
    groq_api_key: str = ""
    gemini_api_key: str = ""
    transcription_timeout_seconds: int = 600
    export_timeout_seconds: int = 600
    min_segment_seconds: float = 1.2
    min_candidate_score: float = 0.35
    preview_top_k: int = 20
    cors_origins: list[str] = field(default_factory=lambda: ["*"])

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

        base.storage_root = Path(storage.get("root", base.storage_root))
        base.jobs_root = Path(storage.get("jobs_root", base.jobs_root))
        base.max_transcription_workers = int(workers.get("max_transcription_workers", base.max_transcription_workers))
        base.max_feature_workers = int(workers.get("max_feature_workers", base.max_feature_workers))
        base.max_clip_workers = int(workers.get("max_clip_workers", base.max_clip_workers))
        base.min_chunk_seconds = int(chunking.get("min_seconds", base.min_chunk_seconds))
        base.max_chunk_seconds = int(chunking.get("max_seconds", base.max_chunk_seconds))
        base.overlap_seconds = int(chunking.get("overlap_seconds", base.overlap_seconds))
        base.retry_count = int(job.get("retry_count", base.retry_count))
        base.transcription_provider = str(job.get("transcription_provider", base.transcription_provider))
        base.transcription_timeout_seconds = int(job.get("transcription_timeout_seconds", base.transcription_timeout_seconds))
        base.groq_api_key = str(os.getenv("GROQ_API_KEY", ""))
        base.gemini_api_key = str(os.getenv("GEMINI_API_KEY", ""))
        base.export_timeout_seconds = int(job.get("export_timeout_seconds", base.export_timeout_seconds))
        base.min_segment_seconds = float(thresholds.get("min_segment_seconds", base.min_segment_seconds))
        base.min_candidate_score = float(thresholds.get("min_candidate_score", base.min_candidate_score))
        base.preview_top_k = int(thresholds.get("preview_top_k", base.preview_top_k))

        base.storage_root = Path(os.getenv("TRIMORA_STORAGE_ROOT", str(base.storage_root)))
        base.jobs_root = Path(os.getenv("TRIMORA_JOBS_ROOT", str(base.jobs_root)))
        return base


settings = Settings.load()
