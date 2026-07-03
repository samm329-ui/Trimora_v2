from __future__ import annotations

import math
from dataclasses import dataclass

from backend.config.worker_limits import MIN_CHUNK_SECONDS, MAX_CHUNK_SECONDS, DEFAULT_OVERLAP_SECONDS


@dataclass(frozen=True)
class ChunkPlan:
    chunk_seconds: int
    overlap_seconds: int
    worker_limit: int


def build_chunk_plan(
    duration_seconds: float,
    speech_density: float = 0.5,
    short_threshold: int = 600,
    medium_threshold: int = 3600,
) -> ChunkPlan:
    duration_seconds = max(duration_seconds, 1.0)

    density_bias = 1.0 + (0.5 - speech_density) * 0.6

    if duration_seconds < short_threshold:
        chunk = 30
        workers = 3
    elif duration_seconds < medium_threshold:
        chunk = 45
        workers = 5
    else:
        chunk = 90
        workers = 5

    chunk = int(max(MIN_CHUNK_SECONDS, min(MAX_CHUNK_SECONDS, round(chunk * density_bias))))
    workers = int(max(1, min(5, workers)))

    overlap = max(DEFAULT_OVERLAP_SECONDS, round(DEFAULT_OVERLAP_SECONDS + (1 - speech_density) * 2))
    return ChunkPlan(chunk_seconds=chunk, overlap_seconds=overlap, worker_limit=workers)


def estimate_speech_density(text: str) -> float:
    letters = sum(ch.isalpha() for ch in text)
    spaces = sum(ch.isspace() for ch in text)
    total = max(len(text), 1)
    return min(1.0, max(0.1, (letters + spaces * 0.2) / total))
