from __future__ import annotations

import logging


from backend.models.clip import ClipCandidate
from backend.models.feature import SegmentFeatures
from backend.models.segment import AtomicSegment
from backend.utils.text_utils import transcript_snippet
from backend.config.ranking_config import (
    PRUNING_MAX_HOOKS,
    PRUNING_MAX_BODIES,
    PRUNING_MAX_ENDINGS,
    PRUNING_MIN_SEGMENT_SCORE,
)
from backend.config.thresholds import SCORING_WEIGHTS

logger = logging.getLogger(__name__)


class ScoringService:
    def _prune_segments(
        self,
        segments: list[AtomicSegment],
        features: list[SegmentFeatures],
    ) -> dict:
        feature_map = {f.segment_id: f for f in features}

        def feature_score(seg: AtomicSegment) -> float:
            f = feature_map.get(seg.id)
            return f.total_score if f else 0.0

        hooks = sorted(
            [s for s in segments if s.kind == "hook" and feature_score(s) >= PRUNING_MIN_SEGMENT_SCORE],
            key=feature_score, reverse=True,
        )
        bodies = sorted(
            [s for s in segments if s.kind == "body" and feature_score(s) >= PRUNING_MIN_SEGMENT_SCORE],
            key=feature_score, reverse=True,
        )
        endings = sorted(
            [s for s in segments if s.kind == "ending" and feature_score(s) >= PRUNING_MIN_SEGMENT_SCORE],
            key=feature_score, reverse=True,
        )

        pruned_hooks = hooks[:PRUNING_MAX_HOOKS]
        pruned_bodies = bodies[:PRUNING_MAX_BODIES]
        pruned_endings = endings[:PRUNING_MAX_ENDINGS]

        before = len(hooks) * len(bodies) * len(endings)
        after = len(pruned_hooks) * len(pruned_bodies) * len(pruned_endings)
        reduction = ((before - after) / max(before, 1)) * 100

        logger.info(
            f"Pruning: hooks {len(hooks)}->{len(pruned_hooks)}, "
            f"bodies {len(bodies)}->{len(pruned_bodies)}, "
            f"endings {len(endings)}->{len(pruned_endings)}, "
            f"combinations {before}->{after} ({reduction:.1f}% reduction)"
        )

        return {
            "hooks": pruned_hooks,
            "bodies": pruned_bodies,
            "endings": pruned_endings,
            "pruned_stats": {
                "hooks_before": len(hooks),
                "hooks_after": len(pruned_hooks),
                "bodies_before": len(bodies),
                "bodies_after": len(pruned_bodies),
                "endings_before": len(endings),
                "endings_after": len(pruned_endings),
                "combinations_before": before,
                "combinations_after": after,
            },
        }

    def generate_candidates(
        self,
        segments: list[AtomicSegment],
        features: list[SegmentFeatures],
        top_k: int = 20,
        min_score: float = 0.35,
    ) -> list[ClipCandidate]:
        feature_map = {f.segment_id: f for f in features}
        pruned = self._prune_segments(segments, features)
        hooks = pruned["hooks"]
        bodies = pruned["bodies"]
        endings = pruned["endings"]

        if not hooks or not bodies or not endings:
            logger.warning("Not enough segments to generate candidates after pruning")
            return []

        candidates: list[ClipCandidate] = []
        for h in hooks:
            for b in bodies:
                for e in endings:
                    if not (h.start <= b.start <= e.start):
                        continue
                    if h.end > b.start or b.end > e.start:
                        continue
                    gap1 = b.start - h.end
                    gap2 = e.start - b.end
                    if gap1 > 30 or gap2 > 30:
                        continue

                    duration = max(e.end - h.start, 1.0)
                    hook_score = feature_map.get(h.id).total_score if h.id in feature_map else 0.5
                    body_score = feature_map.get(b.id).total_score if b.id in feature_map else 0.5
                    ending_score = feature_map.get(e.id).total_score if e.id in feature_map else 0.5
                    flow_score = self._flow_score(h, b, e)

                    total_score = (
                        hook_score * SCORING_WEIGHTS["hook"]
                        + body_score * SCORING_WEIGHTS["body"]
                        + ending_score * SCORING_WEIGHTS["ending"]
                        + flow_score * SCORING_WEIGHTS["flow"]
                    )

                    total_score = self._apply_duration_penalty(total_score, duration)

                    if total_score < min_score:
                        continue

                    snippet = transcript_snippet([h.text, b.text, e.text], limit=24)
                    candidates.append(
                        ClipCandidate(
                            id=f"clip_{h.id}_{b.id}_{e.id}",
                            title=f"{h.kind.title()} / {b.kind.title()} / {e.kind.title()}",
                            hook_start=h.start,
                            hook_end=h.end,
                            body_start=b.start,
                            body_end=b.end,
                            ending_start=e.start,
                            ending_end=e.end,
                            duration=round(duration, 3),
                            hook_score=round(hook_score, 4),
                            body_score=round(body_score, 4),
                            ending_score=round(ending_score, 4),
                            flow_score=round(flow_score, 4),
                            total_score=round(total_score, 4),
                            status="preview",
                            transcript_snippet=snippet,
                            hook_text=h.text,
                            body_text=b.text,
                            ending_text=e.text,
                        )
                    )
        candidates.sort(key=lambda c: c.total_score, reverse=True)
        return candidates[:top_k]

    def _apply_duration_penalty(self, score: float, duration: float) -> float:
        if duration < 15:
            return score * 0.5
        elif duration < 30:
            return score * 0.8
        elif duration <= 60:
            return score * 1.0
        elif duration <= 90:
            return score * 0.9
        else:
            return score * 0.7

    def _flow_score(self, hook: AtomicSegment, body: AtomicSegment, ending: AtomicSegment) -> float:
        gap1 = max(0.0, body.start - hook.end)
        gap2 = max(0.0, ending.start - body.end)
        penalty = min(0.6, (gap1 + gap2) / 300)
        return round(max(0.1, 0.95 - penalty), 4)
