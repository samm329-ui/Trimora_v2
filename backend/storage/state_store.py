from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.storage.file_store import FileStore


class StateStore:
    def __init__(self, file_store: FileStore):
        self.file_store = file_store

    def read(self, path: Path, default: Any = None) -> Any:
        return self.file_store.read_json(path, default)

    def write(self, path: Path, data: Any) -> None:
        self.file_store.atomic_write_json(path, data)
