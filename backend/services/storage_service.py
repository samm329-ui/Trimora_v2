from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from backend.storage.file_store import FileStore


class StorageService:
    """Storage abstraction layer for job data."""

    def __init__(self, root: Path):
        self.root = root
        self.file_store = FileStore(root)

    def save_job_data(self, job_id: str, data_type: str, payload: Any) -> Path:
        """Save data to a job's subdirectory."""
        path = self.get_job_path(job_id, data_type)
        self.file_store.write_json(path, payload)
        return path

    def load_job_data(self, job_id: str, data_type: str) -> Any:
        """Load data from a job's subdirectory."""
        path = self.get_job_path(job_id, data_type)
        return self.file_store.read_json(path)

    def get_job_path(self, job_id: str, subpath: str) -> Path:
        """Get full path for a job's subpath."""
        return self.root / job_id / subpath

    def list_jobs(self) -> list[str]:
        """List all job IDs."""
        if not self.root.exists():
            return []
        return [d.name for d in self.root.iterdir() if d.is_dir()]

    def cleanup_job(self, job_id: str) -> None:
        """Remove a job and all its data."""
        job_path = self.root / job_id
        if job_path.exists():
            shutil.rmtree(job_path)

    def get_job_size(self, job_id: str) -> int:
        """Get total size of a job's data in bytes."""
        job_path = self.root / job_id
        if not job_path.exists():
            return 0
        return sum(f.stat().st_size for f in job_path.rglob("*") if f.is_file())
