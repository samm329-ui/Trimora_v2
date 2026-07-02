from __future__ import annotations

import hashlib
import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None
        self._cache: dict[str, np.ndarray] = {}

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            logger.info(f"Loaded embedding model: {self.model_name}")
        except Exception:
            logger.warning("sentence-transformers unavailable, using TF-IDF fallback")
            self._model = None
        return self._model

    def _cache_key(self, text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()

    def embed(self, text: str) -> np.ndarray:
        key = self._cache_key(text)
        if key in self._cache:
            return self._cache[key]
        model = self._load_model()
        if model is not None:
            vec = model.encode(text, normalize_embeddings=True)
        else:
            vec = self._tfidf_embed(text)
        self._cache[key] = vec
        return vec

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        model = self._load_model()
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []
        results: list[Optional[np.ndarray]] = [None] * len(texts)

        for i, t in enumerate(texts):
            key = self._cache_key(t)
            if key in self._cache:
                results[i] = self._cache[key]
            else:
                uncached_indices.append(i)
                uncached_texts.append(t)

        if uncached_texts:
            if model is not None:
                vectors = model.encode(
                    uncached_texts, normalize_embeddings=True,
                    batch_size=32, show_progress_bar=False,
                )
            else:
                vectors = [self._tfidf_embed(t) for t in uncached_texts]
            for idx, vec in zip(uncached_indices, vectors):
                key = self._cache_key(texts[idx])
                self._cache[key] = vec
                results[idx] = vec

        return [r for r in results if r is not None]

    def clear_cache(self):
        self._cache.clear()

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        return 0.0 if norm_a == 0 or norm_b == 0 else float(dot / (norm_a * norm_b))

    @staticmethod
    def vector_magnitude(a: np.ndarray) -> float:
        return float(np.linalg.norm(a))

    @staticmethod
    def _tfidf_embed(text: str, dim: int = 384) -> np.ndarray:
        words = text.lower().split()
        if not words:
            return np.zeros(dim)
        vec = np.zeros(dim)
        for word in words:
            idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % dim
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec
