from __future__ import annotations

from backend.models.story import StoryCoverage


class CoverageAnalyzer:
    def compute_coverage(self, validated_stories, rejected_stories, all_segments):
        all_ids = {s.id for s in all_segments}
        segment_stories: dict[str, list[str]] = {}
        for story in validated_stories:
            for sid in story.segment_ids:
                segment_stories.setdefault(sid, []).append(story.story_id)
        for story in rejected_stories:
            for sid in story.segment_ids:
                segment_stories.setdefault(sid, []).append(story.story_id)

        fully = partial = unused_count = 0
        unused_ids: list[str] = []
        for sid in all_ids:
            count = len(segment_stories.get(sid, []))
            if count == 0:
                unused_count += 1
                unused_ids.append(sid)
            elif count == 1:
                fully += 1
            else:
                partial += 1

        covered = fully + partial
        unused_segs = [s for s in all_segments if s.id in unused_ids]
        unused_dur = sum(s.end - s.start for s in unused_segs)
        potential = max(0, int(unused_dur / 30))

        return StoryCoverage(
            total_segments=len(all_ids),
            covered_segments=covered,
            coverage_score=round(covered / max(len(all_ids), 1), 4),
            fully_covered=fully,
            partially_covered=partial,
            unused=unused_count,
            unused_segments=sorted(unused_ids),
            unused_duration=round(unused_dur, 3),
            unused_stories=len(rejected_stories),
            potential_additional_shorts=potential,
        )
