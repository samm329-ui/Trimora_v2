# backend/core/artifact.py

from dataclasses import dataclass, field
from typing import Optional, TypeVar, Generic
from enum import Enum
import hashlib
import json
import time

T = TypeVar("T")


class ArtifactStatus(Enum):
    SUCCESS = "success"
    ERROR = "error"


class ErrorSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


@dataclass(frozen=True)
class Artifact(Generic[T]):
    """Single generic artifact type. All artifacts are Artifact[DataType]."""
    artifact_id: str
    version: int
    created_at: float
    data: T
    parent_id: Optional[str] = None
    parent_hash: Optional[str] = None
    status: ArtifactStatus = ArtifactStatus.SUCCESS
    metadata: dict = field(default_factory=dict)

    def compute_hash(self) -> str:
        content = json.dumps({
            "version": self.version,
            "data": self.data if isinstance(self.data, dict) else str(self.data),
        }, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def validate(self) -> list[str]:
        errors = []
        if not self.artifact_id:
            errors.append("artifact_id is empty")
        if self.version < 1:
            errors.append("version must be >= 1")
        return errors


@dataclass(frozen=True)
class ErrorArtifact:
    """First-class error with severity and structured metadata."""
    reason: str
    stage: str
    severity: ErrorSeverity = ErrorSeverity.ERROR
    stacktrace: str = ""
    partial_artifact: Optional[Artifact] = None
    recoverable: bool = False
    error_code: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class ObjectiveResult:
    """Structured result from objective scoring."""
    score: float = 0.5
    confidence: float = 0.5
    status: str = "success"
    latency_ms: float = 0.0
    error: Optional[str] = None


def generate_deterministic_id(
    parent_hash: str,
    stage_name: str,
    version: int,
    output_hash: str = "",
) -> str:
    """Deterministic artifact ID based on parent, stage, version, AND output content."""
    content = f"{parent_hash}:{stage_name}:{version}:{output_hash}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def compute_output_hash(data) -> str:
    """Compute content hash of artifact output data for deterministic IDs."""
    content = json.dumps(
        data if isinstance(data, dict) else str(data),
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(content.encode()).hexdigest()[:16]
