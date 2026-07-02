from __future__ import annotations

from time import perf_counter

from backend.models.learning import AnalyticsSummary


class AnalyticsPipeline:
    def summarize(
        self,
        started_at: float,
        number_of_chunks: int,
        number_of_candidates: int,
        number_of_final_clips: int,
        worker_utilization: float = 0.0,
        failure_points: list[str] | None = None,
        quality_notes: list[str] | None = None,
    ) -> AnalyticsSummary:
        return AnalyticsSummary(
            processing_time_seconds=round(perf_counter() - started_at, 3),
            number_of_chunks=number_of_chunks,
            number_of_candidates=number_of_candidates,
            number_of_final_clips=number_of_final_clips,
            worker_utilization=worker_utilization,
            failure_points=failure_points or [],
            quality_notes=quality_notes or [],
        )
