from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass
class PipelineEvent:
    job_id: str
    name: str
    payload: dict[str, Any]


class EventBus:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[PipelineEvent] = asyncio.Queue()

    async def publish(self, event: PipelineEvent) -> None:
        await self.queue.put(event)

    async def next(self) -> PipelineEvent:
        return await self.queue.get()
