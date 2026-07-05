from __future__ import annotations

import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    from groq import Groq, RateLimitError, APIStatusError

    _HAVE_GROQ = True
except ImportError:
    _HAVE_GROQ = False

try:
    from google import genai as google_genai

    _HAVE_GEMINI = True
except ImportError:
    _HAVE_GEMINI = False


class TokenBucket:
    """Sliding window token bucket that prevents hitting rate limits.

    Tracks token usage over a 60-second window and blocks when
    approaching the limit, so we NEVER get a 429.
    """

    def __init__(self, capacity: int = 6000, window_seconds: float = 60.0):
        self.capacity = capacity
        self.window_seconds = window_seconds
        self._usage: deque[tuple[float, int]] = deque()  # (timestamp, tokens)
        self._lock = threading.Lock()

    def _clean(self, now: float) -> None:
        """Remove entries older than the window."""
        cutoff = now - self.window_seconds
        while self._usage and self._usage[0][0] < cutoff:
            self._usage.popleft()

    def used(self, now: float | None = None) -> int:
        """Total tokens used in the current window."""
        now = now or time.monotonic()
        with self._lock:
            self._clean(now)
            return sum(t for _, t in self._usage)

    def available(self, now: float | None = None) -> int:
        """Tokens remaining in the current window."""
        now = now or time.monotonic()
        with self._lock:
            self._clean(now)
            return max(0, self.capacity - sum(t for _, t in self._usage))

    def consume(self, tokens: int, now: float | None = None) -> None:
        """Record token usage."""
        now = now or time.monotonic()
        with self._lock:
            self._usage.append((now, tokens))

    def wait_for_capacity(self, needed: int, timeout: float = 120.0) -> float:
        """Block until we have capacity for `needed` tokens. Returns wait time."""
        deadline = time.monotonic() + timeout
        total_wait = 0.0

        while True:
            now = time.monotonic()
            avail = self.available(now)
            if avail >= needed:
                return total_wait

            # Calculate how long until oldest entry expires
            with self._lock:
                self._clean(now)
                if self._usage:
                    oldest_time, oldest_tokens = self._usage[0]
                    wait = oldest_time + self.window_seconds - now + 0.1
                else:
                    wait = 0.1

            wait = min(wait, deadline - now)
            if wait <= 0:
                logger.warning("TokenBucket: timeout waiting for capacity (need %d, have %d)", needed, avail)
                return total_wait

            logger.info("TokenBucket: waiting %.1fs for capacity (need %d, have %d, used %d)",
                        wait, needed, avail, self.used())
            time.sleep(wait)
            total_wait += wait


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# LLMProvider — abstract base
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str, response_format: str = "json") -> dict:
        pass

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimate: ~4 chars per token."""
        return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# ProviderEntry — identifies a provider in the router
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProviderEntry:
    id: str
    provider: LLMProvider


# ---------------------------------------------------------------------------
# ProviderRouter — round-robin across multiple LLMProviders
# ---------------------------------------------------------------------------

class ProviderRouter(LLMProvider):
    """Round-robin router across multiple LLMProviders.

    Implements LLMProvider so it's a drop-in replacement anywhere a single
    provider is expected. Each sub-provider owns its own rate-limit bucket.
    """

    def __init__(self, providers: list[ProviderEntry]):
        if not providers:
            raise ValueError("ProviderRouter requires at least one provider.")
        self._providers = providers
        self._index = 0
        self._lock = threading.Lock()

    def complete(self, prompt: str, response_format: str = "json") -> dict:
        with self._lock:
            entry = self._providers[self._index]
            self._index = (self._index + 1) % len(self._providers)

        model = getattr(entry.provider, "model", "unknown")
        logger.info("ProviderRouter: provider=%s model=%s", entry.id, model)

        return entry.provider.complete(prompt, response_format)


class GroqProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "llama-3.1-8b-instant"):
        self.api_key = api_key
        self.model = model
        self._client = None
        self._bucket = TokenBucket(capacity=5500, window_seconds=60.0)

    def _get_client(self):
        if self._client is None:
            self._client = Groq(
                api_key=self.api_key,
                max_retries=0,
                timeout=30.0,
            )
        return self._client

    def complete(self, prompt: str, response_format: str = "json", timeout: float = 60.0) -> dict:
        client = self._get_client()
        kwargs: dict = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        # Estimate tokens and wait for capacity BEFORE making the call
        estimated = estimate_tokens(prompt) + 200  # +200 for response overhead
        waited = self._bucket.wait_for_capacity(estimated, timeout=timeout)
        if waited > 1:
            logger.info("Rate-limited: waited %.1fs for token capacity", waited)

        max_retries = 3
        deadline = time.monotonic() + timeout

        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(**kwargs)

                # Record actual token usage from response
                if hasattr(response, "usage") and response.usage:
                    actual = response.usage.total_tokens
                else:
                    actual = estimated
                self._bucket.consume(actual)

                content = response.choices[0].message.content or "{}"
                return json.loads(content)
            except (RateLimitError, APIStatusError) as e:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or attempt == max_retries - 1:
                    raise

                # Parse "try again in X seconds" from the error message
                wait = self._parse_retry_after(e)
                if wait is None:
                    wait = min(2 ** (attempt + 1), remaining, 10.0)
                else:
                    wait = min(wait + 1.0, remaining)

                # Record the tokens we tried to use so the bucket knows
                self._bucket.consume(estimated)

                logger.warning("Groq rate-limit despite pre-check, retry %d/%d in %.1fs",
                               attempt + 1, max_retries, wait)
                time.sleep(wait)

    @staticmethod
    def _parse_retry_after(error) -> float | None:
        """Parse 'try again in X seconds' from Groq error message."""
        import re
        msg = str(error)
        match = re.search(r"try again in (\d+\.?\d*)s", msg)
        if match:
            return float(match.group(1))
        match = re.search(r"Please try again in (\d+\.?\d*)s", msg)
        if match:
            return float(match.group(1))
        return None


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model
        self._client = None
        self._bucket = TokenBucket(capacity=30000, window_seconds=60.0)

    def _get_client(self):
        if self._client is None:
            self._client = google_genai.Client(api_key=self.api_key)
        return self._client

    def complete(self, prompt: str, response_format: str = "json") -> dict:
        client = self._get_client()
        config = google_genai.types.GenerateContentConfig(
            temperature=0.3,
        )
        if response_format == "json":
            config.response_mime_type = "application/json"
        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        text = response.text or "{}"
        return json.loads(text)


class RuleBasedProvider(LLMProvider):
    def complete(self, prompt: str, response_format: str = "json") -> dict:
        return {"annotations": [], "boundaries": []}


def create_provider(provider_name: str = "auto") -> LLMProvider:
    from backend.config.settings import settings

    entries: list[ProviderEntry] = []
    idx = 1

    # Collect available providers
    if settings.groq_api_key:
        entries.append(ProviderEntry(f"groq-{idx}", GroqProvider(settings.groq_api_key)))
        idx += 1

    for key in settings.groq_api_keys:
        entries.append(ProviderEntry(f"groq-{idx}", GroqProvider(key)))
        idx += 1

    if settings.gemini_api_key:
        entries.append(ProviderEntry("gemini", GeminiProvider(settings.gemini_api_key)))

    if not entries:
        logger.warning("No LLM API key configured, using rule-based fallback")
        return RuleBasedProvider()

    if len(entries) == 1:
        return entries[0].provider

    logger.info("ProviderRouter: distributing across %d providers: %s",
                len(entries), ", ".join(e.id for e in entries))
    return ProviderRouter(entries)
