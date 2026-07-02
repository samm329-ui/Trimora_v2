from __future__ import annotations

from pydantic import BaseModel, Field


class AtomicSegment(BaseModel):
    id: str
    start: float
    end: float
    text: str
    kind: str = "body"
    order: int = 0
    score: float = 0.0
    features: dict[str, float] = Field(default_factory=dict)
