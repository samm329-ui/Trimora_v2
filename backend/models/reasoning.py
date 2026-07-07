# backend/models/reasoning.py

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class EventRole(Enum):
    HOOK = "hook"
    BODY = "body"
    ENDING = "ending"
    REACTION = "reaction"
    TRANSITION = "transition"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Event:
    id: str = ""
    text: str = ""
    start: float = 0.0
    end: float = 0.0
    role: EventRole = EventRole.UNKNOWN
    confidence: float = 0.0
    signals: list = field(default_factory=list)


@dataclass(frozen=True)
class Evidence:
    id: str = ""
    event_id: str = ""
    evidence_type: str = ""
    value: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ClipHypothesis:
    id: str = ""
    event_ids: list = field(default_factory=list)
    strategy: str = ""
    score: float = 0.0
    reasoning: str = ""
    metadata: dict = field(default_factory=dict)
