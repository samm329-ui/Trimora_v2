from __future__ import annotations

from backend.models.clip import ClipCandidate, PreviewManifest


class PreviewService:
    def build_preview(self, job_id: str, candidates: list[ClipCandidate], top_k: int) -> PreviewManifest:
        return PreviewManifest(job_id=job_id, clips=candidates[:top_k])
