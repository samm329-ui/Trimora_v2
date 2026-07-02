from __future__ import annotations

from backend.services.scoring_service import ScoringService
from backend.models.segment import AtomicSegment
from backend.models.feature import SegmentFeatures


class ClipWorker:
    def __init__(self, service: ScoringService):
        self.service = service

    def process(self, segments: list[AtomicSegment], features: list[SegmentFeatures]):
        return self.service.generate_candidates(segments, features)
