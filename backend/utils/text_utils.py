from __future__ import annotations

import re
from typing import Iterable


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str) -> list[str]:
    cleaned = normalize_text(text)
    if not cleaned:
        return []
    return [s.strip() for s in _SENTENCE_SPLIT.split(cleaned) if s.strip()]


def transcript_snippet(parts: Iterable[str], limit: int = 18) -> str:
    tokens = []
    for part in parts:
        for token in part.split():
            tokens.append(token)
            if len(tokens) >= limit:
                return " ".join(tokens)
    return " ".join(tokens)
