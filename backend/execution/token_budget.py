from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field

from backend.config.models import ModelConfig

logger = logging.getLogger(__name__)


@dataclass
class TokenReservation:
    """Tracks a token budget reservation."""

    reservation_id: str
    tokens: int
    created_at: float
    expires_at: float


class TokenBudget:
    """Reservation-based token budget with async waiting.

    Uses asyncio.Condition for efficient async waiting instead of polling.
    Supports reservation/commit/rollback model (like DB transactions).
    """

    def __init__(self, model_config: ModelConfig):
        self.config = model_config
        self._usage: deque[tuple[float, int]] = deque()
        self._reservations: dict[str, TokenReservation] = {}
        self._lock = asyncio.Lock()
        self._budget_released = asyncio.Condition(self._lock)
        self._next_id = 0

    def _clean(self, now: float) -> None:
        """Remove expired entries from usage and reservations."""
        cutoff = now - 60.0
        while self._usage and self._usage[0][0] < cutoff:
            self._usage.popleft()

        expired_reservations = [
            rid
            for rid, r in self._reservations.items()
            if now > r.expires_at
        ]
        for rid in expired_reservations:
            self._reservations.pop(rid, None)

    def _used_tokens(self) -> int:
        return sum(tokens for _, tokens in self._usage)

    async def reserve(self, tokens: int, timeout: float = 30.0) -> TokenReservation | None:
        """Reserve token budget. Uses condition variable for efficient waiting."""
        async with self._budget_released:
            deadline = time.monotonic() + timeout

            while True:
                now = time.monotonic()
                self._clean(now)

                current_usage = self._used_tokens()
                current_reservations = sum(r.tokens for r in self._reservations.values())
                total_committed = current_usage + current_reservations

                if total_committed + tokens <= self.config.safe_tpm:
                    self._next_id += 1
                    reservation = TokenReservation(
                        reservation_id=f"res_{self._next_id}_{now:.3f}",
                        tokens=tokens,
                        created_at=now,
                        expires_at=now + 60.0,
                    )
                    self._reservations[reservation.reservation_id] = reservation
                    return reservation

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    logger.warning(
                        "TokenBudget: timeout waiting for capacity (need %d, used %d, reserved %d, safe_tpm %d)",
                        tokens, current_usage, current_reservations, self.config.safe_tpm,
                    )
                    return None

                try:
                    await asyncio.wait_for(
                        self._budget_released.wait(),
                        timeout=min(remaining, 1.0),
                    )
                except asyncio.TimeoutError:
                    continue

    async def commit(self, reservation_id: str, actual_tokens: int) -> None:
        """Commit reservation with actual usage. Supports partial commit."""
        async with self._budget_released:
            reservation = self._reservations.pop(reservation_id, None)
            if reservation is None:
                return

            self._usage.append((time.monotonic(), actual_tokens))

            if abs(reservation.tokens - actual_tokens) > reservation.tokens * 0.3:
                logger.info(
                    "TokenBudget: reservation diff reserved=%d actual=%d",
                    reservation.tokens,
                    actual_tokens,
                )

            self._budget_released.notify_all()

    async def rollback(self, reservation_id: str) -> None:
        """Rollback reservation (nothing consumed)."""
        async with self._budget_released:
            self._reservations.pop(reservation_id, None)
            self._budget_released.notify_all()

    def current_usage(self) -> int:
        """Current committed token usage."""
        now = time.monotonic()
        self._clean(now)
        return self._used_tokens()
