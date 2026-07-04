from __future__ import annotations

import logging

import numpy as np

from backend.models.topic_block import PriorityBlock, PriorityQueue, TopicBlock

logger = logging.getLogger(__name__)


class PriorityRanker:
    def rank(self, blocks: list[TopicBlock]) -> PriorityQueue:
        """
        Rank blocks by priority for job scheduling.

        This ONLY affects job scheduling (parallel workers, resource allocation).
        It NEVER influences the semantic pipeline order.
        """
        priority_blocks: list[PriorityBlock] = []

        for block in blocks:
            score = 0.0

            duration = block.end - block.start
            if 10 <= duration <= 45:
                score += 0.3
            elif 5 <= duration <= 60:
                score += 0.2
            else:
                score += 0.1

            avg_words = float(np.mean([len(s.text.split()) for s in block.segments]))
            if 10 <= avg_words <= 40:
                score += 0.2

            if any("?" in s.text for s in block.segments):
                score += 0.2

            if any(any(c.isdigit() for c in s.text) for s in block.segments):
                score += 0.1

            if block.start > 30 and block.end < 180:
                score += 0.1

            priority_blocks.append(PriorityBlock(
                block_id=block.original_block_index,
                priority=self._score_to_priority(score),
                score=score,
            ))

        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_blocks = sorted(priority_blocks, key=lambda b: priority_order.get(b.priority, 1))

        timeline_order = [block.original_block_index for block in blocks]

        logger.info("Ranked %d blocks: %d high, %d medium, %d low",
                     len(blocks),
                     sum(1 for b in priority_blocks if b.priority == "high"),
                     sum(1 for b in priority_blocks if b.priority == "medium"),
                     sum(1 for b in priority_blocks if b.priority == "low"))

        return PriorityQueue(blocks=sorted_blocks, timeline_order=timeline_order)

    @staticmethod
    def _score_to_priority(score: float) -> str:
        if score >= 0.6:
            return "high"
        elif score >= 0.4:
            return "medium"
        else:
            return "low"
