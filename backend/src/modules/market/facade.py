"""What market gives its neighbours: the key rate in force on a day. products move the
catalog rates by it, decision prices offers and checks the support program cap with it."""

from datetime import date
from typing import Protocol

from src.modules.market.application.dto.key_rates import KeyRateDTO, KeyRateOrigin

__all__ = ["KeyRateDTO", "KeyRateOrigin", "MarketFacade"]


class MarketFacade(Protocol):
    async def key_rate(self, day: date | None = None) -> KeyRateDTO:
        """In force on `day` (today in Moscow by default); nothing entered — `KEY_RATE`."""
        ...
