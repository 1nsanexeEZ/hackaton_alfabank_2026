from datetime import date
from typing import Protocol

from src.modules.market.domain.key_rate import KeyRate


class KeyRateRepository(Protocol):
    async def on(self, day: date) -> KeyRate | None:
        """The rate in force on `day`: the latest `effective_from` not after it."""
        ...

    async def get(self, effective_from: date) -> KeyRate | None: ...

    async def list_all(self) -> list[KeyRate]:
        """Newest `effective_from` first."""
        ...

    async def add(self, rate: KeyRate) -> None: ...

    async def remove(self, rate: KeyRate) -> None: ...
