# backend/objectives/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from backend.core.artifact import ObjectiveResult


@dataclass(frozen=True)
class ObjectiveMetadata:
    priority: int = 0
    phase: str = "baseline"
    dependencies: list = field(default_factory=list)
    minimum_data: int = 0
    expected_latency_ms: float = 10.0
    deterministic: bool = True
    cacheable: bool = True
    description: str = ""
    baseline_only: bool = True


class Objective(ABC):
    @abstractmethod
    def objective_id(self) -> str:
        pass

    @abstractmethod
    def metadata(self) -> ObjectiveMetadata:
        pass

    @abstractmethod
    def score(self, candidate: dict, context: dict) -> ObjectiveResult:
        pass
