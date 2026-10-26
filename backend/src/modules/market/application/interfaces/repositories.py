from datetime import date, datetime
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

    async def unannounced_until(self, day: date) -> list[KeyRate]:
        """In force by `day` (`effective_from ≤ day`), but KeyRateChanged did not go out yet."""
        ...

    async def mark_announced(self, days: list[date], at: datetime) -> None: ...
