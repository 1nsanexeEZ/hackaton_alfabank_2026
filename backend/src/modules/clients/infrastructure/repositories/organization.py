"""Companies with their members: the Organization aggregate in two tables.

Methods taking an AccessContext are row-level filtered by the caller's
policies (`org_member`: only companies the user is a member of); the rest are
internal lookups for facades and seeds.
"""

from collections import defaultdict
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.access.access_context import AccessContext
from src.core.access.apply_helper import apply_access_context
from src.core.exceptions.exceptions import ConflictError
from src.core.infrastructure.database.mixins import utcnow
from src.modules.clients.application.interfaces.repositories import OrganizationRepository
from src.modules.clients.domain.organization import Organization
from src.modules.clients.infrastructure.database.models import MemberModel, OrganizationModel
from src.modules.clients.infrastructure.repositories.mappers import (
    member_values,
    organization_to_entity,
    organization_values,
)


class SqlAlchemyOrganizationRepository(OrganizationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, organization_id: UUID, access: AccessContext | None = None
    ) -> Organization | None:
        query = select(OrganizationModel).where(OrganizationModel.id == organization_id)
        stmt = query if access is None else apply_access_context(query, OrganizationModel, access)
        models = await self._load(stmt)
        return models[0] if models else None

    async def list_visible(self, access: AccessContext) -> list[Organization]:
        query = select(OrganizationModel).order_by(OrganizationModel.name, OrganizationModel.id)
        return await self._load(apply_access_context(query, OrganizationModel, access))

    async def list_for_member(self, account_id: UUID) -> list[Organization]:
        ids = select(MemberModel.organization_id).where(MemberModel.account_id == account_id)
        stmt = select(OrganizationModel).where(OrganizationModel.id.in_(ids))
        return await self._load(stmt.order_by(OrganizationModel.name, OrganizationModel.id))

    async def get_by_inn(self, inn: str) -> Organization | None:
        models = await self._load(select(OrganizationModel).where(OrganizationModel.inn == inn))
        return models[0] if models else None

    async def member_organization_ids(self, account_id: UUID) -> frozenset[UUID]:
        stmt = select(MemberModel.organization_id).where(MemberModel.account_id == account_id)
        return frozenset((await self._session.scalars(stmt)).all())

    async def add(self, org: Organization) -> None:
        requisites = org.requisites
        self._session.add(
            OrganizationModel(
                id=org.id,
                inn=requisites.inn.value,
                ogrn=requisites.ogrn.value,
                legal_form=requisites.legal_form.value,
                registered_at=org.registered_at,
                version=org.version,
                **organization_values(org),
            )
        )
        # Members reference the company: its row goes first.
        await self._session.flush()
        for member in org.members:
            self._session.add(
                MemberModel(
                    organization_id=org.id, account_id=member.account_id, **member_values(member)
                )
            )
        await self._session.flush()

    async def save(self, org: Organization) -> None:
        """Optimistic locking: a concurrent change of the same company (e.g. two
        managers removing each other) gets a ConflictError instead of breaking
        the invariants checked on a stale copy."""
        result = await self._session.execute(
            update(OrganizationModel)
            .where(OrganizationModel.id == org.id, OrganizationModel.version == org.version)
            .values(version=org.version + 1, updated_at=utcnow(), **organization_values(org))
        )
        if result.rowcount != 1:  # type: ignore[attr-defined]
            raise ConflictError(
                "Organization was changed by someone else, retry",
                details={"code": "version_conflict"},
            )
        org.version += 1

        stored = {
            m.account_id: m
            for m in (
                await self._session.scalars(
                    select(MemberModel).where(MemberModel.organization_id == org.id)
                )
            ).all()
        }
        current = {m.account_id: m for m in org.members}
        removed = set(stored) - set(current)
        if removed:
            await self._session.execute(
                delete(MemberModel)
                .where(MemberModel.organization_id == org.id, MemberModel.account_id.in_(removed))
                .execution_options(synchronize_session="fetch")
            )
        for account_id, member in current.items():
            model = stored.get(account_id)
            if model is None:
                self._session.add(
                    MemberModel(
                        organization_id=org.id, account_id=account_id, **member_values(member)
                    )
                )
            else:
                for name, value in member_values(member).items():
                    setattr(model, name, value)
        await self._session.flush()

    async def _load(self, stmt: Any) -> list[Organization]:
        # populate_existing: a company saved earlier in this session is read fresh.
        fresh = {"populate_existing": True}
        models: Sequence[OrganizationModel] = (
            await self._session.scalars(stmt.execution_options(**fresh))
        ).all()
        if not models:
            return []
        rows = await self._session.scalars(
            select(MemberModel)
            .where(MemberModel.organization_id.in_([m.id for m in models]))
            .execution_options(**fresh)
        )
        members: dict[UUID, list[MemberModel]] = defaultdict(list)
        for row in rows.all():
            members[row.organization_id].append(row)
        return [organization_to_entity(m, members[m.id]) for m in models]
