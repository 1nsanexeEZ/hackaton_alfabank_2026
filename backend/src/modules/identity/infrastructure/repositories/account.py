from collections.abc import Collection, Sequence
from uuid import UUID

from sqlalchemy import ColumnElement, exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Executable

from src.core.access.access_context import AccessContext
from src.core.access.apply_helper import apply_access_context
from src.modules.identity.application.interfaces.repositories import AccountRepository
from src.modules.identity.domain.account import Account
from src.modules.identity.domain.login_policy import Login
from src.modules.identity.infrastructure.database.models import AccountModel, RoleModel
from src.modules.identity.infrastructure.repositories.mappers import (
    account_to_entity,
    account_to_row,
    aware,
    update_account_row,
)


class SqlAlchemyAccountRepository(AccountRepository):
    """Methods taking an AccessContext are row-level filtered by the caller's
    policies. The rest are internal lookups (login, /me) and see every live row."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, access: AccessContext, limit: int, offset: int) -> Sequence[Account]:
        page = (
            select(AccountModel)
            .order_by(AccountModel.created_at, AccountModel.id)
            .limit(limit)
            .offset(offset)
        )
        stmt = apply_access_context(page, AccountModel, access)
        rows = (await self._session.scalars(stmt)).unique().all()
        return [account_to_entity(row) for row in rows]

    async def get(self, access: AccessContext, account_id: UUID) -> Account | None:
        stmt = apply_access_context(
            select(AccountModel).where(AccountModel.id == account_id), AccountModel, access
        )
        return await self._one(stmt)

    async def get_active_by_id(self, account_id: UUID) -> Account | None:
        return await self._one_active(AccountModel.id == account_id)

    async def get_active_by_login(self, login: Login) -> Account | None:
        if login.email is not None:
            return await self._one_active(AccountModel.email == login.email)
        if login.phone is not None:
            return await self._one_active(AccountModel.phone == login.phone)
        return None

    async def list_active_by_emails(self, emails: Collection[str]) -> Sequence[Account]:
        stmt = select(AccountModel).where(
            AccountModel.email.in_(emails), AccountModel.entity_is_not_deleted()
        )
        rows = (await self._session.scalars(stmt)).unique().all()
        return [account_to_entity(row) for row in rows]

    async def login_taken(
        self,
        email: str | None,
        phone: str | None,
        exclude_id: UUID | None = None,
    ) -> bool:
        conditions = []
        if email is not None:
            conditions.append(AccountModel.email == email)
        if phone is not None:
            conditions.append(AccountModel.phone == phone)
        if not conditions:
            return False
        stmt = select(AccountModel.id).where(AccountModel.entity_is_not_deleted())
        stmt = stmt.where(conditions[0] if len(conditions) == 1 else conditions[0] | conditions[1])
        if exclude_id is not None:
            stmt = stmt.where(AccountModel.id != exclude_id)
        return (await self._session.scalar(select(exists(stmt)))) or False

    async def add(self, account: Account) -> None:
        row = account_to_row(account)
        self._session.add(row)
        await self._session.flush()
        account.created_at = aware(row.created_at)

    async def save(self, account: Account) -> None:
        row = await self._row(account.id)
        update_account_row(row, account)
        if row.role_id != account.role.id:
            row.role = await self._session.get_one(RoleModel, account.role.id)
        await self._session.flush()

    async def _one(self, stmt: Executable) -> Account | None:
        row: AccountModel | None = (await self._session.scalars(stmt)).unique().one_or_none()
        return None if row is None else account_to_entity(row)

    async def _one_active(self, condition: ColumnElement[bool]) -> Account | None:
        return await self._one(
            select(AccountModel).where(condition, AccountModel.entity_is_not_deleted())
        )

    async def _row(self, account_id: UUID) -> AccountModel:
        # Already in the session: the use case loaded the account before changing it.
        return await self._session.get_one(AccountModel, account_id)
