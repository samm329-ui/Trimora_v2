from __future__ import annotations

from backend.services.feature_service import FeatureService
from backend.models.segment import AtomicSegment


class FeatureWorker:
    def __init__(self, service: FeatureService):
        self.service = service

    def process(self, segment: AtomicSegment):
        return self.service.compute_features(segment)
