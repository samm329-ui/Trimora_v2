from __future__ import annotations

from pydantic import BaseModel, Field


class ClipCandidate(BaseModel):
    id: str
    title: str
    hook_start: float
    hook_end: float
    body_start: float
    body_end: float
    ending_start: float
    ending_end: float
    duration: float
    hook_score: float
    body_score: float
    ending_score: float
    flow_score: float
    total_score: float
    status: str = "candidate"
    transcript_snippet: str = ""
    hook_text: str = ""
    body_text: str = ""
    ending_text: str = ""


class PreviewManifest(BaseModel):
    job_id: str
    clips: list[ClipCandidate] = Field(default_factory=list)
