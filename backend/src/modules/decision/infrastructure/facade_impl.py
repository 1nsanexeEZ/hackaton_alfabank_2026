from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.domain.clock import Clock
from src.modules.decision.facade import (
    ClientDecisionDTO,
    DecisionDTO,
    FounderPrescreenDTO,
    PreApprovedOfferDTO,
    ProjectAssessmentDTO,
)
from src.modules.decision.infrastructure.mappers import (
    client_decision_dto,
    decision_dto,
    pre_approved_dto,
    prescreen_dto,
    project_dto,
)
from src.modules.decision.infrastructure.repository import (
    SqlAlchemyDecisionRepository,
    SqlAlchemyFounderPrescreenRepository,
    SqlAlchemyPreApprovedOfferRepository,
    SqlAlchemyProjectAssessmentRepository,
)


class DecisionFacadeImpl:
    """Последнее решение по заявке (ручное перекрывает авто), действующие предодобрения,
    предскрин учредителя и проектная оценка стартапа."""

    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self._decisions = SqlAlchemyDecisionRepository(session)
        self._offers = SqlAlchemyPreApprovedOfferRepository(session)
        self._prescreens = SqlAlchemyFounderPrescreenRepository(session)
        self._projects = SqlAlchemyProjectAssessmentRepository(session)
        self._clock = clock

    async def get_founder_prescreen(self, organization_id: UUID) -> FounderPrescreenDTO | None:
        prescreen = await self._prescreens.latest_for_organization(organization_id)
        return prescreen_dto(prescreen, self._clock.now()) if prescreen is not None else None

    async def get_decision(self, application_id: UUID) -> DecisionDTO | None:
        result = await self._decisions.latest_for_application(application_id)
        return decision_dto(result) if result is not None else None

    async def get_decisions(self, application_ids: Sequence[UUID]) -> dict[UUID, DecisionDTO]:
        results = await self._decisions.latest_for_applications(application_ids)
        return {application_id: decision_dto(r) for application_id, r in results.items()}

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

    async def get_project_assessment(self, organization_id: UUID) -> ProjectAssessmentDTO | None:
        assessment = await self._projects.latest_for_organization(organization_id)
        return project_dto(assessment, self._clock.now()) if assessment is not None else None
