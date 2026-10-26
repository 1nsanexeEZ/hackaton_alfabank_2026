from datetime import date
from decimal import Decimal

from src.modules.market.facade import KeyRateDTO


class FakeMarketFacade:
    """The same key rate on every day, as from the settings."""

    def __init__(self, value: Decimal = Decimal("16.50")) -> None:
        self.value = value

    async def key_rate(self, day: date | None = None) -> KeyRateDTO:
        return KeyRateDTO(self.value, None, "settings")
