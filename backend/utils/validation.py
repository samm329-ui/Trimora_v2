from __future__ import annotations

from pathlib import Path


ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


def is_allowed_video(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS
