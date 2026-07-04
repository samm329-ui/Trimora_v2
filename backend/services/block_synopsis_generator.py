from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from backend.models.topic_block import TopicBlock
from backend.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class BlockSynopsisGenerator:
    def __init__(self, embedding_service: EmbeddingService):
        self.embedder = embedding_service

    def generate_synopsis(self, block: TopicBlock) -> str:
        """
        Generate a deterministic, descriptive synopsis for a topic block.

        Fixed template for debugging and versioning:
        Duration, Segments, Opening, Closing, Frequent terms, Named entities.
        """
        duration = block.end - block.start
        segment_count = len(block.segments)

        opening = block.segments[0].text[:100]
        closing = block.segments[-1].text[:100]

        frequent_terms = self._extract_frequent_terms(block)
        entities = self._extract_entities(block)

        synopsis = (
            f"Duration: {duration:.1f}s\n"
            f"Segments: {segment_count}\n"
            f"Opening: {opening}\n"
            f"Closing: {closing}\n"
            f"Frequent terms: {', '.join(frequent_terms[:5])}\n"
            f"Named entities: {', '.join(entities[:3]) if entities else 'none'}"
        )

        return synopsis

    def find_representative_excerpt(self, block: TopicBlock) -> str:
        """
        Find the most representative segment in the block.

        Strategy: segment whose embedding is closest to block centroid.
        Falls back to highest information density if embeddings unavailable.
        """
        if not block.segments:
            return ""

        if block.embedding:
            block_emb = np.array(block.embedding)
            best_segment = block.segments[0]
            best_similarity = -1.0
            candidates: list[tuple[float, object]] = []

            for seg in block.segments:
                seg_emb = self.embedder.embed(seg.text)
                sim = self.embedder.cosine_similarity(block_emb, seg_emb)
                candidates.append((sim, seg))
                if sim > best_similarity:
                    best_similarity = sim
                    best_segment = seg

            margin = 0.02
            near_best = [s for sim, s in candidates if sim >= best_similarity - margin]
            if len(near_best) > 1:
                return self._highest_density_segment(near_best)

            return best_segment.text[:150]

        return self._highest_density_segment(block.segments)

    @staticmethod
    def _highest_density_segment(segments: list) -> str:
        best_segment = segments[0]
        best_density = 0.0

        for seg in segments:
            words = seg.text.split()
            duration = max(seg.end - seg.start, 0.1)
            density = len(words) / duration
            if density > best_density:
                best_density = density
                best_segment = seg

        return best_segment.text[:150]

    @staticmethod
    def _extract_frequent_terms(block: TopicBlock) -> list[str]:
        word_freq: dict[str, int] = {}
        for seg in block.segments:
            words = seg.text.lower().split()
            for word in words:
                if len(word) > 3:
                    word_freq[word] = word_freq.get(word, 0) + 1

        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, _ in sorted_words[:5]]

    @staticmethod
    def _extract_entities(block: TopicBlock) -> list[str]:
        entities: set[str] = set()
        for seg in block.segments:
            words = seg.text.split()
            for word in words:
                if len(word) > 2 and word[0].isupper():
                    entities.add(word)
        return list(entities)[:3]

    @staticmethod
    def save_synopses(blocks: list[TopicBlock], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "blocks": [
                {
                    "block_id": block.original_block_index,
                    "start": block.start,
                    "end": block.end,
                    "segment_count": len(block.segments),
                    "segment_ids": [s.id for s in block.segments],
                    "synopsis": block.synopsis,
                    "representative_excerpt": block.representative_excerpt,
                    "structural_confidence": block.structural_confidence,
                }
                for block in blocks
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def load_synopses(path: Path) -> list[dict]:
        if not path.exists():
            return []
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("blocks", [])
