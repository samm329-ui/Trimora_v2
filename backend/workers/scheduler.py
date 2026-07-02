from __future__ import annotations

from dataclasses import dataclass

from backend.workers.worker_pool import WorkerPool


@dataclass
class TaskPlan:
    max_workers: int
    chunk_seconds: int
    overlap_seconds: int


class Scheduler:
    def __init__(self, max_workers: int):
        self.max_workers = max_workers

    def build_pool(self, limit: int | None = None) -> WorkerPool:
        return WorkerPool(limit or self.max_workers)
