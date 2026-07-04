from __future__ import annotations

from typing import Any


class SegmentRepository:
    """
    Read-only repository for segment data.
    Created once per job. Passed to PromptBuilder.build().
    PromptBuilder resolves IDs through this.
    """

    def __init__(self, segments: list[Any], blocks: list[Any], annotations: Any = None):
        self._segments = {s.id: s for s in segments}
        self._blocks = {b.original_block_index: b for b in blocks}
        self._annotations = annotations

    def get_segment(self, segment_id: int) -> Any | None:
        return self._segments.get(segment_id)

    def get_segments(self, ids: tuple[int, ...]) -> list[Any]:
        return [self._segments[i] for i in ids if i in self._segments]

    def get_block(self, block_index: int) -> Any | None:
        return self._blocks.get(block_index)

    def get_annotations(self, segment_ids: tuple[int, ...]) -> list[Any]:
        if not self._annotations:
            return []
        return [a for a in self._annotations.annotations if a.segment_id in segment_ids]

    @property
    def segment_count(self) -> int:
        return len(self._segments)

    @property
    def block_count(self) -> int:
        return len(self._blocks)
