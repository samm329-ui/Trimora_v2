from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from backend.config.settings import settings
from backend.models.job import JobRecord, JobStatus
from backend.storage.file_store import FileStore


class JobStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or settings.jobs_root)
        self.file_store = FileStore(self.root)
        self.file_store.ensure_dir(self.root)

    def create_job(self, filename: str) -> JobRecord:
        job_id = str(uuid.uuid4())
        workdir = self.root / job_id
        self._init_job_dirs(workdir)

        record = JobRecord(
            job_id=job_id,
            status=JobStatus.uploaded,
            progress=0.0,
            source_filename=filename,
            source_path=str(workdir / "input" / filename),
            workdir=str(workdir),
            state_path=str(workdir / "state.json"),
            metadata_path=str(workdir / "metadata.json"),
        )
        self.save_job(record)
        self.file_store.write_json(workdir / "metadata.json", record.model_dump(mode="json"))
        return record

    def _init_job_dirs(self, workdir: Path) -> None:
        for rel in [
            "input", "audio", "audio/chunks", "transcript", "segments", "features",
            "graph", "clips", "learning", "analytics", "exports",
        ]:
            self.file_store.ensure_dir(workdir / rel)

    def job_dir(self, job_id: str) -> Path:
        return self.root / job_id

    def load_job(self, job_id: str) -> JobRecord:
        workdir = self.job_dir(job_id)
        data = self.file_store.read_json(workdir / "state.json")
        if not data:
            raise FileNotFoundError(f"Job {job_id} not found")
        return JobRecord.model_validate(data)

    def save_job(self, job: JobRecord) -> None:
        job.touch()
        workdir = Path(job.workdir or self.job_dir(job.job_id))
        payload = job.model_dump(mode="json")
        self.file_store.atomic_write_json(workdir / "state.json", payload)
        self.file_store.atomic_write_json(workdir / "metadata.json", payload)

    def update_job(self, job_id: str, **changes: Any) -> JobRecord:
        job = self.load_job(job_id)
        for key, value in changes.items():
            setattr(job, key, value)
        self.save_job(job)
        return job

    def set_status(self, job_id: str, status: JobStatus, progress: float | None = None, error: str | None = None) -> JobRecord:
        job = self.load_job(job_id)
        job.status = status
        if progress is not None:
            job.progress = max(0.0, min(1.0, progress))
        if error is not None:
            job.error = error
        if status in {JobStatus.complete, JobStatus.failed, JobStatus.cancelled}:
            from datetime import datetime, timezone
            job.completed_at = datetime.now(timezone.utc)
        self.save_job(job)
        return job
