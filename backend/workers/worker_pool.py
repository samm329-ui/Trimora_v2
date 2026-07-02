from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Iterable, TypeVar

T = TypeVar("T")
R = TypeVar("R")


@dataclass
class WorkerPoolConfig:
    limit: int = 15


class WorkerPool:
    def __init__(self, limit: int):
        self.limit = max(1, limit)

    async def run(self, items: Iterable[T], handler: Callable[[T], Awaitable[R]]) -> list[R]:
        semaphore = asyncio.Semaphore(self.limit)
        results: list[R] = []

        async def one(item: T) -> R:
            async with semaphore:
                return await handler(item)

        tasks = [asyncio.create_task(one(item)) for item in items]
        results = await asyncio.gather(*tasks)
        return results
