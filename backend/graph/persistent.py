# backend/graph/persistent.py

from dataclasses import dataclass, field
from backend.core.artifact import Artifact, generate_deterministic_id, compute_output_hash
from backend.models.data import GraphData
import time
import json


@dataclass
class GraphVersion:
    version: int
    artifact: Artifact
    timestamp: float
    description: str = ""


class PersistentKnowledgeGraph:
    """Knowledge graph with versioning support."""

    def __init__(self):
        self._versions: list[GraphVersion] = []
        self._current: Artifact = None

    async def execute(self, inputs: dict) -> Artifact[GraphData]:
        key = list(inputs.keys())[0] if inputs else None
        artifact = inputs.get(key) if key else None
        if artifact is None:
            raise ValueError("PersistentKnowledgeGraph requires an input artifact")

        self._current = artifact
        version_num = len(self._versions) + 1

        self._versions.append(GraphVersion(
            version=version_num,
            artifact=artifact,
            timestamp=time.time(),
        ))

        return artifact

    def get_version(self, version: int) -> Artifact:
        for v in self._versions:
            if v.version == version:
                return v.artifact
        return None

    def get_current(self) -> Artifact:
        return self._current

    def version_count(self) -> int:
        return len(self._versions)
