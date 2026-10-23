from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.access.access_context import AccessContext
from src.core.access.apply_helper import apply_access_context
from src.modules.identity.application.interfaces.repositories import RoleRepository
from src.modules.identity.domain.entities import Role
from src.modules.identity.infrastructure.database.models import AccountModel, RoleModel
from src.modules.identity.infrastructure.repositories.mappers import (
    aware,
    role_to_entity,
    role_to_row,
    update_role_row,
)


class SqlAlchemyRoleRepository(RoleRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, access: AccessContext) -> Sequence[Role]:
        stmt = apply_access_context(select(RoleModel).order_by(RoleModel.name), RoleModel, access)
        return [role_to_entity(row) for row in (await self._session.scalars(stmt)).all()]

    async def get(self, access: AccessContext, role_id: UUID) -> Role | None:
        stmt = apply_access_context(
            select(RoleModel).where(RoleModel.id == role_id), RoleModel, access
        )
        row: RoleModel | None = (await self._session.scalars(stmt)).one_or_none()
        return None if row is None else role_to_entity(row)

    async def get_by_id(self, role_id: UUID) -> Role | None:
        row = await self._session.get(RoleModel, role_id)
        return None if row is None else role_to_entity(row)

    async def get_by_name(self, name: str) -> Role | None:
        stmt = select(RoleModel).where(RoleModel.name == name)
        row = (await self._session.scalars(stmt)).one_or_none()
        return None if row is None else role_to_entity(row)

    async def is_in_use(self, role_id: UUID) -> bool:
        stmt = select(func.count()).select_from(AccountModel).where(AccountModel.role_id == role_id)
        return bool(await self._session.scalar(stmt))

    async def add(self, role: Role) -> None:
        row = role_to_row(role)
        self._session.add(row)
        await self._session.flush()
        role.created_at, role.updated_at = aware(row.created_at), aware(row.updated_at)

    async def save(self, role: Role) -> None:
        row = await self._session.get_one(RoleModel, role.id)
        update_role_row(row, role)
        await self._session.flush()
        role.updated_at = aware(row.updated_at)

    async def delete(self, role: Role) -> None:
        await self._session.delete(await self._session.get_one(RoleModel, role.id))
