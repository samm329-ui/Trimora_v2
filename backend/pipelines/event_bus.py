from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Awaitable


@dataclass
class PipelineEvent:
    job_id: str
    name: str
    payload: dict[str, Any]


class EventBus:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[PipelineEvent] = asyncio.Queue()
        self._subscribers: list[Callable[[PipelineEvent], Awaitable[None]]] = []

    async def publish(self, event: PipelineEvent) -> None:
        await self.queue.put(event)
        # Notify subscribers
        for subscriber in self._subscribers:
            try:
                await subscriber(event)
            except Exception:
                pass  # Subscriber errors don't break the bus

    async def next(self) -> PipelineEvent:
        return await self.queue.get()

    def subscribe(self, fn: Callable[[PipelineEvent], Awaitable[None]]) -> None:
        self._subscribers.append(fn)

    def unsubscribe(self, fn: Callable[[PipelineEvent], Awaitable[None]]) -> None:
        self._subscribers = [s for s in self._subscribers if s is not fn]
