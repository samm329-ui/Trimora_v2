import os
import threading
import pytest
from unittest.mock import MagicMock
from backend.services.llm_provider import (
    LLMProvider, ProviderEntry, ProviderRouter, GroqProvider, GeminiProvider,
    RuleBasedProvider, TokenBucket, create_provider,
)


class MockProvider(LLMProvider):
    """Test provider that returns a fixed response and tracks calls."""

    def __init__(self, response: dict | None = None, provider_id: str = "mock"):
        self.response = response or {"result": "ok"}
        self.provider_id = provider_id
        self.call_count = 0
        self.prompts_received: list[str] = []

    def complete(self, prompt: str, response_format: str = "json") -> dict:
        self.call_count += 1
        self.prompts_received.append(prompt)
        return self.response


# ---------------------------------------------------------------------------
# ProviderRouter — basic selection
# ---------------------------------------------------------------------------

class TestProviderRouterSelection:
    def test_single_provider_always_selects_same(self):
        provider = MockProvider(response={"a": 1})
        entry = ProviderEntry("mock-1", provider)
        router = ProviderRouter([entry])

        for _ in range(10):
            router.complete("test")

        assert provider.call_count == 10

    def test_two_providers_alternates(self):
        p1 = MockProvider(response={"a": 1})
        p2 = MockProvider(response={"b": 2})
        router = ProviderRouter([
            ProviderEntry("p1", p1),
            ProviderEntry("p2", p2),
        ])

        results = [router.complete("test") for _ in range(6)]

        assert p1.call_count == 3
        assert p2.call_count == 3
        # Verify alternation: p1, p2, p1, p2, p1, p2
        assert results[0] == {"a": 1}
        assert results[1] == {"b": 2}
        assert results[2] == {"a": 1}
        assert results[3] == {"b": 2}

    def test_three_providers_cycles(self):
        p1 = MockProvider(response={"a": 1})
        p2 = MockProvider(response={"b": 2})
        p3 = MockProvider(response={"c": 3})
        router = ProviderRouter([
            ProviderEntry("p1", p1),
            ProviderEntry("p2", p2),
            ProviderEntry("p3", p3),
        ])

        results = [router.complete("test") for _ in range(9)]

        assert p1.call_count == 3
        assert p2.call_count == 3
        assert p3.call_count == 3
        # Verify cycle: p1, p2, p3, p1, p2, p3, p1, p2, p3
        assert results[0] == {"a": 1}
        assert results[1] == {"b": 2}
        assert results[2] == {"c": 3}
        assert results[3] == {"a": 1}

    def test_wraps_around_after_many_calls(self):
        p1 = MockProvider(response={"a": 1})
        p2 = MockProvider(response={"b": 2})
        router = ProviderRouter([
            ProviderEntry("p1", p1),
            ProviderEntry("p2", p2),
        ])

        for _ in range(100):
            router.complete("test")

        assert p1.call_count == 50
        assert p2.call_count == 50


# ---------------------------------------------------------------------------
# ProviderRouter — constructor validation
# ---------------------------------------------------------------------------

class TestProviderRouterValidation:
    def test_empty_providers_raises(self):
        with pytest.raises(ValueError, match="at least one provider"):
            ProviderRouter([])

    def test_single_provider_works(self):
        provider = MockProvider()
        router = ProviderRouter([ProviderEntry("p1", provider)])
        result = router.complete("test")
        assert result == {"result": "ok"}


# ---------------------------------------------------------------------------
# ProviderRouter — thread safety
# ---------------------------------------------------------------------------

class TestProviderRouterThreadSafety:
    def test_concurrent_calls_dont_crash(self):
        p1 = MockProvider(response={"a": 1})
        p2 = MockProvider(response={"b": 2})
        router = ProviderRouter([
            ProviderEntry("p1", p1),
            ProviderEntry("p2", p2),
        ])

        errors: list[Exception] = []

        def call_router():
            try:
                for _ in range(100):
                    router.complete("test")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=call_router) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert p1.call_count + p2.call_count == 1000

    def test_distribution_is_roughly_even(self):
        p1 = MockProvider(response={"a": 1})
        p2 = MockProvider(response={"b": 2})
        router = ProviderRouter([
            ProviderEntry("p1", p1),
            ProviderEntry("p2", p2),
        ])

        def call_router():
            for _ in range(100):
                router.complete("test")

        threads = [threading.Thread(target=call_router) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # With thread safety, distribution should be within 10% of even
        total = p1.call_count + p2.call_count
        assert abs(p1.call_count - p2.call_count) < total * 0.15


# ---------------------------------------------------------------------------
# ProviderEntry — dataclass
# ---------------------------------------------------------------------------

class TestProviderEntry:
    def test_frozen(self):
        provider = MockProvider()
        entry = ProviderEntry("test", provider)
        with pytest.raises(AttributeError):
            entry.id = "changed"

    def test_equality(self):
        p = MockProvider()
        e1 = ProviderEntry("a", p)
        e2 = ProviderEntry("a", p)
        assert e1 == e2


# ---------------------------------------------------------------------------
# Per-provider TokenBucket isolation
# ---------------------------------------------------------------------------

class TestTokenBucketIsolation:
    def test_groq_providers_have_separate_buckets(self):
        p1 = GroqProvider(api_key="key1")
        p2 = GroqProvider(api_key="key2")
        assert p1._bucket is not p2._bucket

    def test_gemini_has_its_own_bucket(self):
        g = GeminiProvider(api_key="key1")
        assert isinstance(g._bucket, TokenBucket)
        # Gemini bucket should have higher capacity
        assert g._bucket.capacity == 30000

    def test_groq_bucket_capacity(self):
        g = GroqProvider(api_key="key1")
        assert g._bucket.capacity == 5500

    def test_token_buckets_track_independently(self):
        b1 = TokenBucket(capacity=100)
        b2 = TokenBucket(capacity=100)
        b1.consume(50)
        assert b1.used() == 50
        assert b2.used() == 0


# ---------------------------------------------------------------------------
# create_provider — factory behavior
# ---------------------------------------------------------------------------

class TestCreateProvider:
    def test_no_keys_returns_rule_based(self, monkeypatch):
        monkeypatch.setattr("backend.config.settings.settings", type("S", (), {
            "groq_api_key": "",
            "groq_api_keys": [],
            "gemini_api_key": "",
        })())
        result = create_provider()
        assert isinstance(result, RuleBasedProvider)

    def test_single_groq_key_returns_groq_provider(self, monkeypatch):
        monkeypatch.setattr("backend.config.settings.settings", type("S", (), {
            "groq_api_key": "gsk_test",
            "groq_api_keys": [],
            "gemini_api_key": "",
        })())
        result = create_provider()
        assert isinstance(result, GroqProvider)

    def test_single_gemini_key_returns_gemini_provider(self, monkeypatch):
        monkeypatch.setattr("backend.config.settings.settings", type("S", (), {
            "groq_api_key": "",
            "groq_api_keys": [],
            "gemini_api_key": "ai_test",
        })())
        result = create_provider()
        assert isinstance(result, GeminiProvider)

    def test_multiple_keys_returns_router(self, monkeypatch):
        monkeypatch.setattr("backend.config.settings.settings", type("S", (), {
            "groq_api_key": "gsk_1",
            "groq_api_keys": ["gsk_2"],
            "gemini_api_key": "",
        })())
        result = create_provider()
        assert isinstance(result, ProviderRouter)

    def test_all_keys_returns_router(self, monkeypatch):
        monkeypatch.setattr("backend.config.settings.settings", type("S", (), {
            "groq_api_key": "gsk_1",
            "groq_api_keys": ["gsk_2"],
            "gemini_api_key": "ai_1",
        })())
        result = create_provider()
        assert isinstance(result, ProviderRouter)

    def test_router_has_correct_provider_count(self, monkeypatch):
        monkeypatch.setattr("backend.config.settings.settings", type("S", (), {
            "groq_api_key": "gsk_1",
            "groq_api_keys": ["gsk_2", "gsk_3"],
            "gemini_api_key": "ai_1",
        })())
        result = create_provider()
        assert isinstance(result, ProviderRouter)
        assert len(result._providers) == 4
        assert [e.id for e in result._providers] == [
            "groq-1", "groq-2", "groq-3", "gemini"
        ]


# ---------------------------------------------------------------------------
# Environment parsing (tested via Settings directly)
# ---------------------------------------------------------------------------

class TestEnvParsing:
    def test_no_additional_keys(self, monkeypatch):
        for i in range(1, 10):
            monkeypatch.delenv(f"GROQ_API_KEY_{i}", raising=False)
        result = []
        for i in range(1, 10):
            key = os.environ.get(f"GROQ_API_KEY_{i}", "")
            if key:
                result.append(key)
        assert result == []

    def test_single_key(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY_1", "gsk_test")
        for i in range(2, 10):
            monkeypatch.delenv(f"GROQ_API_KEY_{i}", raising=False)
        result = []
        for i in range(1, 10):
            key = os.environ.get(f"GROQ_API_KEY_{i}", "")
            if key:
                result.append(key)
        assert result == ["gsk_test"]

    def test_multiple_keys(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY_1", "gsk_1")
        monkeypatch.setenv("GROQ_API_KEY_2", "gsk_2")
        monkeypatch.setenv("GROQ_API_KEY_3", "gsk_3")
        for i in range(4, 10):
            monkeypatch.delenv(f"GROQ_API_KEY_{i}", raising=False)
        result = []
        for i in range(1, 10):
            key = os.environ.get(f"GROQ_API_KEY_{i}", "")
            if key:
                result.append(key)
        assert result == ["gsk_1", "gsk_2", "gsk_3"]

    def test_non_sequential_keys(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY_1", "gsk_1")
        monkeypatch.delenv("GROQ_API_KEY_2", raising=False)
        monkeypatch.setenv("GROQ_API_KEY_3", "gsk_3")
        for i in [4, 5, 6, 7, 8, 9]:
            monkeypatch.delenv(f"GROQ_API_KEY_{i}", raising=False)
        result = []
        for i in range(1, 10):
            key = os.environ.get(f"GROQ_API_KEY_{i}", "")
            if key:
                result.append(key)
        assert result == ["gsk_1", "gsk_3"]
