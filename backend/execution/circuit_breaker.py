from __future__ import annotations

import logging
import time
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker with CLOSED/OPEN/HALF_OPEN states.

    Stops retrying when provider is exhausted. Auto-recovers after open_duration.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        open_duration: float = 60.0,
        half_open_requests: int = 1,
        success_threshold: int = 2,
    ):
        self.failure_threshold = failure_threshold
        self.open_duration = open_duration
        self.half_open_requests = half_open_requests
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_count = 0
        self._opened_at = 0.0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._opened_at >= self.open_duration:
                self._state = CircuitState.HALF_OPEN
                self._half_open_count = 0
                self._success_count = 0
                logger.info("CircuitBreaker: OPEN -> HALF_OPEN")
        return self._state

    def can_execute(self) -> bool:
        """Check if execution is allowed."""
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            return self._half_open_count < self.half_open_requests
        return False

    def record_success(self) -> None:
        """Record a successful execution."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
                logger.info("CircuitBreaker: HALF_OPEN -> CLOSED")
        else:
            self._failure_count = 0

    def record_failure(self, is_rate_limit: bool = False) -> None:
        """Record a failed execution."""
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning("CircuitBreaker: HALF_OPEN -> OPEN")
            return

        self._failure_count += 1
        if is_rate_limit:
            self._failure_count += 1

        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning(
                "CircuitBreaker: CLOSED -> OPEN (failures=%d)",
                self._failure_count,
            )

    def reset(self) -> None:
        """Reset the circuit breaker to CLOSED."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_count = 0
