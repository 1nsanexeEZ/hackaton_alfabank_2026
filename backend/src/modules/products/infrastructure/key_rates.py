from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.facades import FacadeRegistry
from src.modules.market.facade import MarketFacade
from src.modules.products.application.ports import KeyRates


class MarketKeyRates(KeyRates):
    def __init__(self, market: MarketFacade) -> None:
        self._market = market

    async def current(self) -> Decimal:
        return (await self._market.key_rate()).value


def key_rates(facades: FacadeRegistry, session: AsyncSession) -> KeyRates | None:
    """Without the market module (unit tests of products) the catalog rates do not move."""
    return MarketKeyRates(facades.get(MarketFacade, session)) if facades.has(MarketFacade) else None
