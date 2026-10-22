from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.domain.clock import Clock
from src.modules.decision.facade import ClientDecisionDTO, DecisionDTO, PreApprovedOfferDTO
from src.modules.decision.infrastructure.mappers import (
    client_decision_dto,
    decision_dto,
    pre_approved_dto,
)
from src.modules.decision.infrastructure.repository import (
    SqlAlchemyDecisionRepository,
    SqlAlchemyPreApprovedOfferRepository,
)


class DecisionFacadeImpl:
    """Последнее решение по заявке (ручное перекрывает авто) и действующие предодобрения."""

    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self._decisions = SqlAlchemyDecisionRepository(session)
        self._offers = SqlAlchemyPreApprovedOfferRepository(session)
        self._clock = clock

    async def get_decision(self, application_id: UUID) -> DecisionDTO | None:
        result = await self._decisions.latest_for_application(application_id)
        return decision_dto(result) if result is not None else None

    async def get_client_view(self, application_id: UUID) -> ClientDecisionDTO | None:
        result = await self._decisions.latest_for_application(application_id)
        return client_decision_dto(result) if result is not None else None

    async def get_pre_approved(self, organization_id: UUID) -> list[PreApprovedOfferDTO]:
        today = self._clock.now().date()
        return [
            pre_approved_dto(offer)
            for offer in await self._offers.list_for_organization(organization_id)
            if offer.valid_until >= today
        ]
