# backend/strategies/base.py

from abc import ABC, abstractmethod


class ClipStrategy(ABC):
    @abstractmethod
    def strategy_id(self) -> str:
        pass

    @abstractmethod
    async def generate(self, context) -> list:
        pass
