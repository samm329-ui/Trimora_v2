from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.storage.file_store import FileStore


class ManifestStore:
    def __init__(self, file_store: FileStore):
        self.file_store = file_store

    def save_manifest(self, path: Path, payload: Any) -> None:
        self.file_store.atomic_write_json(path, payload)
