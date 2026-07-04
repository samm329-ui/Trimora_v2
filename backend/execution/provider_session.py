from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Callable, Awaitable

from backend.execution.models import ExecutionResult, RequestMetrics
from backend.services.llm_provider import LLMProvider

logger = logging.getLogger(__name__)


class AsyncRateLimiter:
    """
    Async sliding-window token bucket.
    CORRECTION: Lock is only held while reading/updating usage.
    Released before sleeping so other workers can check capacity.
    """

    def __init__(self, capacity: int = 5500, window_seconds: float = 60.0):
        self.capacity = capacity
        self.window_seconds = window_seconds
        self._usage: deque[tuple[float, int]] = deque()
        self._lock = asyncio.Lock()

    def _clean(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._usage and self._usage[0][0] < cutoff:
            self._usage.popleft()

    def _used(self) -> int:
        return sum(tokens for _, tokens in self._usage)

    def _wait_time(self, now: float) -> float:
        if self._usage:
            return min(self.window_seconds - (now - self._usage[0][0]), 1.0)
        return 0.05

    async def acquire(self, needed: int, timeout: float = 120.0) -> float:
        """Acquire token capacity. Returns wait time. Never blocks event loop."""
        start = time.monotonic()
        deadline = start + timeout

        while True:
            now = time.monotonic()
            if now >= deadline:
                logger.warning("AsyncRateLimiter: timeout waiting for capacity (need %d)", needed)
                return now - start

            # Hold lock ONLY while checking and updating usage
            wait_seconds = 0.0
            async with self._lock:
                self._clean(now)
                available = self.capacity - self._used()
                if available >= needed:
                    self._usage.append((now, needed))
                    return now - start
                wait_seconds = self._wait_time(now)

            # Lock released — other workers can check capacity while we sleep
            remaining = deadline - time.monotonic()
            sleep_time = min(wait_seconds, remaining)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)


class ProviderMiddleware:
    """Wraps API calls with middleware chain. Middleware runs before the actual provider call."""

    def __init__(self):
        self._fns: list[Callable[[str, str], Awaitable[str]]] = []

    def add(self, fn: Callable[[str, str], Awaitable[str]]):
        self._fns.append(fn)

    async def execute(self, prompt: str, call_fn: Callable, request_id: str) -> ExecutionResult:
        for fn in self._fns:
            prompt = await fn(prompt, request_id)
        return await call_fn(prompt, request_id)


class ProviderSession:
    """
    Active connection to an LLM provider.
    Owns rate limiting, token estimation, and middleware.
    Created once, lives for app lifetime.
    """

    def __init__(self, provider: LLMProvider, capacity: int = 5500):
        self.provider = provider
        self._rate_limiter = AsyncRateLimiter(capacity=capacity)
        self._middleware = ProviderMiddleware()

    def use(self, middleware_fn: Callable[[str, str], Awaitable[str]]):
        """Register a middleware function."""
        self._middleware.add(middleware_fn)

    async def execute(self, prompt: str, request_id: str) -> ExecutionResult:
        """Execute with middleware chain. Caller provides resolved prompt."""
        return await self._middleware.execute(prompt, self._call_provider, request_id)

    async def _call_provider(self, prompt: str, request_id: str) -> ExecutionResult:
        """Call the actual provider with rate limiting."""
        start = time.monotonic()
        try:
            estimated = self.provider.estimate_tokens(prompt)
            await self._rate_limiter.acquire(estimated)
            raw_response = await asyncio.to_thread(self.provider.complete, prompt)
            completed_at = time.monotonic()
            return ExecutionResult(
                request_id=request_id,
                raw_response=raw_response,
                status="completed",
                metrics=RequestMetrics(
                    started_at=start,
                    completed_at=completed_at,
                    execution_time=completed_at - start,
                    tokens_used=raw_response.get("_usage", {}).get("total_tokens", estimated),
                ),
            )
        except Exception as e:
            completed_at = time.monotonic()
            retryable = _is_retryable(e)
            return ExecutionResult(
                request_id=request_id,
                raw_response={},
                status="failed",
                error=e,
                retryable=retryable,
                metrics=RequestMetrics(
                    started_at=start,
                    completed_at=completed_at,
                    execution_time=completed_at - start,
                ),
            )


def _is_retryable(error: Exception) -> bool:
    """
    Classify whether a provider error is retryable.
    Returns True for transient failures, False for permanent failures.
    """
    error_type = type(error).__name__
    error_msg = str(error).lower()

    # Rate limits — always retryable (with backoff)
    if "rate" in error_msg or "429" in error_msg or "ratelimit" in error_type:
        return True

    # Timeout — retryable
    if "timeout" in error_type or "timeout" in error_msg:
        return True

    # Transient network errors — retryable
    if any(kw in error_msg for kw in ["connection", "network", "reset", "refused", "temporary"]):
        return True

    # API status errors — depends on status code
    if hasattr(error, "status_code"):
        code = error.status_code
        # 4xx (except 429) are permanent failures
        if 400 <= code < 500 and code != 429:
            return False
        # 5xx are retryable
        if 500 <= code < 600:
            return True

    # Invalid response / parsing errors — not retryable (same prompt will fail again)
    if isinstance(error, (ValueError, KeyError, TypeError)):
        return False

    # Default: retryable (assume transient)
    return True
