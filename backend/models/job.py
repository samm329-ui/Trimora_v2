from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    uploaded = "uploaded"
    queued = "queued"
    extracting_audio = "extracting_audio"
    chunking = "chunking"
    transcribing = "transcribing"
    merging = "merging"
    segmenting = "segmenting"
    analyzing = "analyzing"
    scoring = "scoring"
    preview_ready = "preview_ready"
    export_ready = "export_ready"
    complete = "complete"
    cancelled = "cancelled"
    failed = "failed"


class JobRecord(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.uploaded
    progress: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    source_filename: Optional[str] = None
    source_path: Optional[str] = None
    workdir: Optional[str] = None
    state_path: Optional[str] = None
    metadata_path: Optional[str] = None
    retries: int = 0
    cancelled: bool = False
    preview_count: int = 0
    export_count: int = 0
    stats: dict[str, Any] = Field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)
