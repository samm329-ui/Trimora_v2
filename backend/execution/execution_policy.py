from __future__ import annotations

import logging
import time

from backend.execution.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class ExecutionPolicy:
    """Retry, backoff, timeout, and circuit breaker wrapping.

    Owns the resilience logic separate from the scheduler.
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 2.0,
        max_delay: float = 30.0,
        request_timeout: float = 90.0,
        circuit_breaker: CircuitBreaker | None = None,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.request_timeout = request_timeout
        self._circuit_breaker = circuit_breaker or CircuitBreaker()

    def can_execute(self) -> bool:
        """Check if execution is allowed (circuit breaker not open)."""
        return self._circuit_breaker.can_execute()

    def calculate_backoff(self, attempt: int, error: Exception) -> float:
        """Calculate exponential backoff delay for retry attempt."""
        is_rate_limit = "rate" in str(error).lower() or "429" in str(error)
        if is_rate_limit:
            base = self.base_delay * 2
        else:
            base = self.base_delay
        delay = min(base * (2 ** attempt), self.max_delay)
        return delay

    def record_success(self) -> None:
        """Record a successful execution."""
        self._circuit_breaker.record_success()

    def record_failure(self, is_rate_limit: bool = False) -> None:
        """Record a failed execution."""
        self._circuit_breaker.record_failure(is_rate_limit=is_rate_limit)

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        return self._circuit_breaker
