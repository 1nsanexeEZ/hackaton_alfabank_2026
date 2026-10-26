from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.domain.clock import Clock
from src.modules.market.application.dto.key_rates import KeyRateDTO
from src.modules.market.application.use_cases.key_rates import GetKeyRateUseCase
from src.modules.market.facade import MarketFacade
from src.modules.market.infrastructure.repositories.key_rates import SqlAlchemyKeyRateRepository


class MarketFacadeImpl(MarketFacade):
    """One indexed row per call, no cache: a new rate is in force at once."""

    def __init__(self, session: AsyncSession, clock: Clock, fallback: Decimal) -> None:
        self._use_case = GetKeyRateUseCase(SqlAlchemyKeyRateRepository(session), clock, fallback)

    async def key_rate(self, day: date | None = None) -> KeyRateDTO:
        return await self._use_case.execute(day)
