from __future__ import annotations

import asyncio
from pathlib import Path

from backend.models.learning import AnalyticsSummary, LearningEntry
from backend.storage.file_store import FileStore


class LearningPipeline:
    def __init__(self, file_store: FileStore):
        self.file_store = file_store

    def save_job_learning(self, job_dir: Path, job_id: str, accepted_ids: list[str], rejected_ids: list[str], notes: list[str]) -> None:
        learning_dir = job_dir / "learning"
        self.file_store.write_json(
            learning_dir / "labels.json",
            {"accepted": accepted_ids, "rejected": rejected_ids},
        )
        self.file_store.write_json(
            learning_dir / "decision_log.json",
            {"job_id": job_id, "notes": notes},
        )
        self.file_store.write_json(
            learning_dir / "patterns.json",
            {"patterns": []},
        )
        self.file_store.write_json(
            learning_dir / "failures.json",
            {"failures": []},
        )

    async def save_job_learning_async(self, job_dir: Path, job_id: str, accepted_ids: list[str], rejected_ids: list[str], notes: list[str]) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.save_job_learning, job_dir, job_id, accepted_ids, rejected_ids, notes)

    def save_analytics(self, job_dir: Path, summary: AnalyticsSummary) -> None:
        self.file_store.write_json(job_dir / "analytics" / "statistics.json", summary.model_dump(mode="json"))

    async def save_analytics_async(self, job_dir: Path, summary: AnalyticsSummary) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.save_analytics, job_dir, summary)
