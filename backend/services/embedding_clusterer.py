from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from backend.config.settings import settings
from backend.models.topic_block import TopicBlock
from backend.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class EmbeddingClusterer:
    def __init__(
        self,
        embedding_service: EmbeddingService,
        min_window: int | None = None,
        target_window: int | None = None,
        max_window: int | None = None,
        max_duration: float | None = None,
        max_tokens: int | None = None,
        smoothing_window: int | None = None,
        threshold_std: float | None = None,
        z_score_max_std: float | None = None,
    ):
        self.embedder = embedding_service
        self.min_window = min_window or settings.embedding_min_window
        self.target_window = target_window or settings.embedding_target_window
        self.max_window = max_window or settings.embedding_max_window
        self.max_duration = max_duration or settings.embedding_max_duration
        self.max_tokens = max_tokens or settings.embedding_max_tokens
        self.smoothing_window = smoothing_window or settings.embedding_smoothing_window
        self.threshold_std = threshold_std or settings.embedding_threshold_std
        self.z_score_max_std = z_score_max_std or settings.embedding_z_score_max_std

    def cluster(self, segments: list) -> tuple[list[TopicBlock], list[dict]]:
        """
        Cluster segments into topic blocks using sliding window embeddings.

        Returns:
            - blocks: list of TopicBlock in timeline order
            - embeddings_data: list of embedding metadata for persistence
        """
        if len(segments) <= self.min_window:
            block = TopicBlock(
                segments=segments,
                start=segments[0].start,
                end=segments[-1].end,
                original_block_index=0,
                structural_confidence=1.0,
            )
            block.embedding = self._compute_block_embedding(segments)
            return [block], [{"block_id": 0, "embedding": block.embedding}]

        windows = self._create_dynamic_windows(segments)

        window_texts = [self._window_text(w, segments) for w in windows]
        window_embeddings = self.embedder.embed_batch(window_texts)

        similarities = []
        for i in range(1, len(window_embeddings)):
            sim = self.embedder.cosine_similarity(
                window_embeddings[i - 1], window_embeddings[i]
            )
            similarities.append(sim)

        smoothed = self._smooth(similarities, self.smoothing_window)

        mean_sim = float(np.mean(smoothed))
        std_sim = float(np.std(smoothed))
        threshold = mean_sim - (self.threshold_std * std_sim)

        boundaries = self._find_boundaries(smoothed, threshold, mean_sim, std_sim, windows)

        blocks, embeddings_data = self._create_blocks(segments, boundaries)

        logger.info("Clustered %d segments into %d blocks (threshold=%.3f)", len(segments), len(blocks), threshold)
        return blocks, embeddings_data

    def _create_dynamic_windows(self, segments: list) -> list[list[int]]:
        windows: list[list[int]] = []
        i = 0
        while i < len(segments):
            window_size = self.target_window

            window_end = min(i + window_size, len(segments))
            duration = segments[window_end - 1].end - segments[i].start

            if duration > self.max_duration:
                while window_size > self.min_window:
                    window_size -= 1
                    window_end = min(i + window_size, len(segments))
                    duration = segments[window_end - 1].end - segments[i].start
                    if duration <= self.max_duration:
                        break

            window_text = " ".join([segments[j].text for j in range(i, window_end)])
            while window_size > self.min_window and len(window_text) // 4 > self.max_tokens:
                window_size -= 1
                window_end = min(i + window_size, len(segments))
                window_text = " ".join([segments[j].text for j in range(i, window_end)])

            if window_size < self.target_window and duration < 15:
                window_size = min(self.max_window, len(segments) - i)
                window_end = i + window_size

            window_size = min(window_size, len(segments) - i)
            windows.append(list(range(i, i + window_size)))
            i += max(1, window_size - 2)

        return windows

    @staticmethod
    def _smooth(values: list[float], window: int) -> list[float]:
        if len(values) < window:
            return values

        smoothed = []
        for i in range(len(values)):
            start = max(0, i - window // 2)
            end = min(len(values), i + window // 2 + 1)
            avg = float(np.mean(values[start:end]))
            smoothed.append(avg)

        return smoothed

    def _find_boundaries(
        self,
        smoothed: list[float],
        threshold: float,
        mean_sim: float,
        std_sim: float,
        windows: list[list[int]],
    ) -> list[dict]:
        boundaries: list[dict] = [{"index": 0, "structural_confidence": 1.0, "z_score": 0.0}]

        for i, sim in enumerate(smoothed):
            if sim < threshold:
                z_score = (mean_sim - sim) / std_sim if std_sim > 0 else 0.0
                structural_confidence = self._normalize_z_score(z_score)

                boundaries.append({
                    "index": windows[i + 1][0] if i + 1 < len(windows) else len(smoothed),
                    "structural_confidence": structural_confidence,
                    "z_score": z_score,
                })

        return boundaries

    def _normalize_z_score(self, z_score: float) -> float:
        return min(1.0, z_score / self.z_score_max_std)

    def _create_blocks(
        self, segments: list, boundaries: list[dict]
    ) -> tuple[list[TopicBlock], list[dict]]:
        blocks: list[TopicBlock] = []
        embeddings_data: list[dict] = []

        for i in range(len(boundaries) - 1):
            start_idx = boundaries[i]["index"]
            end_idx = boundaries[i + 1]["index"]
            block_segments = segments[start_idx:end_idx]

            if block_segments:
                block_embedding = self._compute_block_embedding(block_segments)

                block = TopicBlock(
                    segments=block_segments,
                    start=block_segments[0].start,
                    end=block_segments[-1].end,
                    original_block_index=i,
                    structural_confidence=boundaries[i + 1]["structural_confidence"],
                    embedding=block_embedding,
                )
                blocks.append(block)

                embeddings_data.append({
                    "block_id": i,
                    "start": block.start,
                    "end": block.end,
                    "embedding": block_embedding,
                })

        return blocks, embeddings_data

    def _compute_block_embedding(self, segments: list) -> list[float]:
        texts = [s.text for s in segments]
        embeddings = self.embedder.embed_batch(texts)
        centroid = np.mean(embeddings, axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm
        return centroid.tolist()

    def _window_text(self, window_indices: list[int], segments: list) -> str:
        return " ".join([segments[i].text for i in window_indices])

    @staticmethod
    def save_embeddings(embeddings_data: list[dict], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "embeddings": embeddings_data,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def load_embeddings(path: Path) -> list[dict]:
        if not path.exists():
            return []
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("embeddings", [])
