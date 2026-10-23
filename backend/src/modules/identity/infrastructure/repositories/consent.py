from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.application.interfaces.repositories import ConsentRepository
from src.modules.identity.domain.entities import Consent
from src.modules.identity.domain.enums import ConsentType
from src.modules.identity.infrastructure.database.models import ConsentModel
from src.modules.identity.infrastructure.repositories.mappers import (
    assign,
    consent_to_entity,
    consent_to_row,
)


class SqlAlchemyConsentRepository(ConsentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for(self, account_id: UUID) -> Sequence[Consent]:
        stmt = (
            select(ConsentModel)
            .where(ConsentModel.account_id == account_id)
            .order_by(ConsentModel.given_at.desc(), ConsentModel.id)
        )
        return [consent_to_entity(row) for row in (await self._session.scalars(stmt)).all()]

    async def list_not_revoked(self, account_id: UUID, type: ConsentType) -> Sequence[Consent]:
        stmt = (
            select(ConsentModel)
            .where(
                ConsentModel.account_id == account_id,
                ConsentModel.type == type,
                ConsentModel.revoked_at.is_(None),
            )
            .order_by(ConsentModel.given_at.desc(), ConsentModel.id)
        )
        return [consent_to_entity(row) for row in (await self._session.scalars(stmt)).all()]

    async def add(self, consent: Consent) -> None:
        self._session.add(consent_to_row(consent))

    async def save(self, consent: Consent) -> None:
        """Only a revocation changes a stored consent."""
        row = await self._session.get_one(ConsentModel, consent.id)
        assign(row, revoked_at=consent.revoked_at)
