# backend/core/artifact.py

from dataclasses import dataclass, field
from typing import Optional, TypeVar, Generic
from enum import Enum, StrEnum
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


# TODO: Separate into PipelineStage, StrategyType, BridgeStage
class ArtifactStage(StrEnum):
    # Pipeline stages
    DEDUP = "dedup"
    SCORES = "scores"
    NARRATIVE = "narrative"
    PORTFOLIO = "portfolio"
    EVALUATION = "evaluation"
    CANDIDATES_FOR_DEDUP = "candidates_for_dedup"
    # Strategy types
    STORY = "story"
    HOOK = "hook"
    REVEAL = "reveal"
    REACTION = "reaction"
    OPINION = "opinion"
    # Bridge adapters
    GRAPH_BRIDGE = "graph_bridge"
    SIGNAL_BRIDGE = "signal_bridge"
    SCORES_BRIDGE = "scores_bridge"
    # Service stages
    GRAPH = "graph"
    ROLES = "roles"
    SIGNALS = "signals"


class PipelineContractError(RuntimeError):
    """Raised when a pipeline stage receives an unexpected artifact type."""

    def __init__(self, stage: ArtifactStage, expected: type, received: type,
                 artifact_id: str = None, parent_id: str = None):
        self.stage = stage
        self.expected = expected
        self.received = received
        self.artifact_id = artifact_id
        self.parent_id = parent_id
        msg = f"{stage.value} expected {expected.__name__}, received {received.__name__}"
        if artifact_id:
            msg += f" (artifact: {artifact_id}"
            if parent_id:
                msg += f", parent: {parent_id}"
            msg += ")"
        super().__init__(msg)


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
    pipeline_version: str = "v1"

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


def validate_artifact_data(data):
    """Extension point for artifact validation. Called by create_artifact when validate=True."""
    pass


def create_artifact(
    data: T,
    stage: ArtifactStage,
    parent: "Artifact" = None,
    version: int = 1,
    validate: bool = True,
) -> Artifact[T]:
    """Centralized artifact creation. Production code should use this instead of Artifact(...)."""
    if validate:
        validate_artifact_data(data)
    parent_hash = parent.compute_hash() if parent else ""
    output_hash = compute_output_hash(data)
    return Artifact(
        artifact_id=generate_deterministic_id(parent_hash, stage, version, output_hash=output_hash),
        version=version,
        created_at=time.time(),
        parent_id=parent.artifact_id if parent else None,
        parent_hash=parent_hash,
        data=data,
    )
