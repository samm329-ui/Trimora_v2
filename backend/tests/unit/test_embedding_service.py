import numpy as np
from backend.services.embedding_service import EmbeddingService


def test_tfidf_embed_returns_vector():
    emb = EmbeddingService._tfidf_embed("Hello world")
    assert isinstance(emb, np.ndarray)
    assert emb.shape == (384,)
    assert np.linalg.norm(emb) > 0


def test_tfidf_embed_normalized():
    emb = EmbeddingService._tfidf_embed("Hello world")
    norm = np.linalg.norm(emb)
    assert abs(norm - 1.0) < 0.001


def test_tfidf_embed_empty():
    emb = EmbeddingService._tfidf_embed("")
    assert np.linalg.norm(emb) == 0.0


def test_cosine_similarity_identical():
    emb = EmbeddingService._tfidf_embed("same text")
    sim = EmbeddingService.cosine_similarity(emb, emb)
    assert abs(sim - 1.0) < 0.001


def test_cosine_similarity_orthogonal():
    a = np.array([1.0, 0.0, 0.0])
    b = np.array([0.0, 1.0, 0.0])
    sim = EmbeddingService.cosine_similarity(a, b)
    assert abs(sim) < 0.001


def test_cosine_similarity_zero_vector():
    a = np.array([0.0, 0.0, 0.0])
    b = np.array([1.0, 0.0, 0.0])
    sim = EmbeddingService.cosine_similarity(a, b)
    assert sim == 0.0


def test_vector_magnitude():
    emb = np.array([3.0, 4.0])
    mag = EmbeddingService.vector_magnitude(emb)
    assert abs(mag - 5.0) < 0.001


def test_embed_caches():
    svc = EmbeddingService()
    e1 = svc.embed("Hello world")
    e2 = svc.embed("Hello world")
    np.testing.assert_array_equal(e1, e2)


def test_embed_batch():
    svc = EmbeddingService()
    texts = ["Hello", "World", "Test"]
    results = svc.embed_batch(texts)
    assert len(results) == 3
    for r in results:
        assert isinstance(r, np.ndarray)
        assert r.shape == (384,)


def test_clear_cache():
    svc = EmbeddingService()
    svc.embed("Hello")
    assert len(svc._cache) == 1
    svc.clear_cache()
    assert len(svc._cache) == 0
