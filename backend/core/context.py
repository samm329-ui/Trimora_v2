# backend/core/context.py

from dataclasses import dataclass, field
from typing import Optional, Any
import logging
import time


@dataclass
class PipelineConfig:
    """Configuration — isolated concern."""
    _values: dict = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def set(self, key: str, value: Any):
        self._values[key] = value

    def to_dict(self) -> dict:
        return dict(self._values)


@dataclass
class MetricsCollector:
    """Metrics — isolated concern."""
    _data: dict = field(default_factory=dict)

    def record(self, name: str, value: float):
        if name not in self._data:
            self._data[name] = []
        self._data[name].append(value)

    def get(self, name: str) -> list:
        return self._data.get(name, [])

    def summary(self) -> dict:
        result = {}
        for name, values in self._data.items():
            if values:
                sorted_v = sorted(values)
                n = len(sorted_v)
                p50_idx = n // 2
                if n % 2 == 0 and n > 0:
                    p50 = (sorted_v[p50_idx - 1] + sorted_v[p50_idx]) / 2
                else:
                    p50 = sorted_v[p50_idx]
                p95_idx = max(0, int(n * 0.95) - 1)
                result[name] = {
                    "p50": p50,
                    "p95": sorted_v[p95_idx],
                    "max": max(sorted_v),
                    "count": n,
                }
        return result

    def to_dict(self) -> dict:
        return dict(self._data)


@dataclass
class CacheStore:
    """Cache — isolated concern."""
    _data: dict = field(default_factory=dict)

    def get(self, key: str) -> Optional[Any]:
        return self._data.get(key)

    def set(self, key: str, value: Any):
        self._data[key] = value

    def has(self, key: str) -> bool:
        return key in self._data

    def clear(self):
        self._data.clear()

    def to_dict(self) -> dict:
        return dict(self._data)


@dataclass
class LoggerAdapter:
    """Logger — isolated concern."""
    _logger: Any = None

    def info(self, msg: str):
        if self._logger:
            self._logger.info(msg)

    def warning(self, msg: str):
        if self._logger:
            self._logger.warning(msg)

    def error(self, msg: str):
        if self._logger:
            self._logger.error(msg)

    def debug(self, msg: str):
        if self._logger:
            self._logger.debug(msg)


@dataclass
class ExecutionContext:
    """Shared context — composes isolated concerns, not a God Object."""
    job_id: str = ""
    config: PipelineConfig = field(default_factory=PipelineConfig)
    metrics: MetricsCollector = field(default_factory=MetricsCollector)
    cache: CacheStore = field(default_factory=CacheStore)
    logger: LoggerAdapter = field(default_factory=LoggerAdapter)
    artifact_registry: dict = field(default_factory=dict)
    evaluation_hooks: list = field(default_factory=list)
    feature_flags: dict = field(default_factory=dict)

    def get_config(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def is_enabled(self, flag: str) -> bool:
        return self.feature_flags.get(flag, False)

    def record_metric(self, name: str, value: float):
        self.metrics.record(name, value)

    def cache_get(self, key: str) -> Optional[Any]:
        return self.cache.get(key)

    def cache_set(self, key: str, value: Any):
        self.cache.set(key, value)

    def log(self, msg: str):
        self.logger.info(msg)


@dataclass(frozen=True)
class PipelineContext:
    """Immutable context passed to strategies — they ask for what they need."""
    graph: Any = None
    evidence: Any = None
    embeddings: Any = None
    signals: Any = None
    transcript: Any = None
    config: dict = field(default_factory=dict)
    feature_flags: dict = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)
