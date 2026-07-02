from __future__ import annotations

from pathlib import Path

from backend.models.learning import LearningEntry, AnalyticsSummary
from backend.storage.file_store import FileStore


class LearningWorker:
    def __init__(self, file_store: FileStore):
        self.file_store = file_store

    def save_decision(self, path: Path, entry: LearningEntry) -> None:
        self.file_store.write_json(path, entry.model_dump(mode="json"))

    def save_analytics(self, path: Path, summary: AnalyticsSummary) -> None:
        self.file_store.write_json(path, summary.model_dump(mode="json"))
