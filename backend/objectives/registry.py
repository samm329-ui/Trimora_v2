# backend/objectives/registry.py

from backend.core.artifact import ObjectiveResult
import time


class ObjectiveRegistry:
    """Registry that executes objectives as a dependency DAG, not a simple loop."""

    def __init__(self):
        self._objectives = {}
        self._metadata = {}

    def register(self, objective):
        self._objectives[objective.objective_id()] = objective
        self._metadata[objective.objective_id()] = objective.metadata()

    def score_all(self, candidate: dict, context: dict) -> dict[str, ObjectiveResult]:
        """Execute objectives respecting dependency order."""
        executed = {}
        results = {}

        # Build dependency graph
        in_degree = {}
        for obj_id, meta in self._metadata.items():
            in_degree[obj_id] = len(meta.dependencies)

        # Topological execution
        ready = [obj_id for obj_id, deg in in_degree.items() if deg == 0]
        remaining = dict(in_degree)

        while ready:
            batch = []
            for obj_id in ready:
                if obj_id in self._objectives:
                    batch.append(obj_id)

            for obj_id in batch:
                objective = self._objectives[obj_id]
                start = time.monotonic()
                try:
                    result = objective.score(candidate, context)
                    result = ObjectiveResult(
                        score=result.score,
                        confidence=result.confidence,
                        status=result.status,
                        latency_ms=(time.monotonic() - start) * 1000,
                        error=result.error,
                    )
                    results[obj_id] = result
                except Exception as e:
                    results[obj_id] = ObjectiveResult(
                        score=0.5, confidence=0.0, status="error",
                        latency_ms=(time.monotonic() - start) * 1000,
                        error=str(e),
                    )
                executed[obj_id] = True

            # Update in-degree for next batch
            ready = []
            for obj_id in remaining:
                if obj_id in executed:
                    continue
                meta = self._metadata[obj_id]
                all_deps_met = all(dep in executed for dep in meta.dependencies)
                if all_deps_met:
                    ready.append(obj_id)

        # Score any remaining objectives that weren't reached (missing deps)
        for obj_id, objective in self._objectives.items():
            if obj_id not in results:
                start = time.monotonic()
                try:
                    result = objective.score(candidate, context)
                    results[obj_id] = ObjectiveResult(
                        score=result.score, confidence=result.confidence,
                        status=result.status,
                        latency_ms=(time.monotonic() - start) * 1000,
                        error=result.error,
                    )
                except Exception as e:
                    results[obj_id] = ObjectiveResult(
                        score=0.5, confidence=0.0, status="error",
                        latency_ms=(time.monotonic() - start) * 1000,
                        error=str(e),
                    )

        return results

    def get_metadata(self, objective_id: str):
        return self._metadata.get(objective_id)

    def list_objectives(self) -> list:
        return [{"id": obj_id, "metadata": meta.__dict__} for obj_id, meta in self._metadata.items()]
