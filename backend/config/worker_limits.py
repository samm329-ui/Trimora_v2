from __future__ import annotations

# Worker pool limits
MAX_TRANSCRIPTION_WORKERS: int = 8  # safety cap; actual count computed by WhisperManager
MAX_FEATURE_WORKERS: int = 15
MAX_CLIP_WORKERS: int = 8
DEFAULT_WORKERS: int = 5

# Chunk limits
MIN_CHUNK_SECONDS: int = 20
MAX_CHUNK_SECONDS: int = 120
DEFAULT_OVERLAP_SECONDS: int = 2
