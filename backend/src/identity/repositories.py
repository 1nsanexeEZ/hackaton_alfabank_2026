from collections.abc import Collection, Sequence
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.access.access_context import AccessContext
from src.core.access.apply_helper import apply_access_context
from src.identity.models import Account, Role


class AccountRepository:
    """Methods taking an AccessContext are row-level filtered by the caller's
    policies. The rest are internal lookups (login, /me) and see every live row."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, access: AccessContext, limit: int, offset: int) -> Sequence[Account]:
        stmt = apply_access_context(select(Account), Account, access)
        stmt = stmt.order_by(Account.created_at, Account.id).limit(limit).offset(offset)
        return (await self._session.scalars(stmt)).unique().all()

    async def get(self, access: AccessContext, account_id: UUID) -> Account | None:
        stmt = apply_access_context(
            select(Account).where(Account.id == account_id), Account, access
        )
        return (await self._session.scalars(stmt)).unique().one_or_none()

    async def get_active_by_id(self, account_id: UUID) -> Account | None:
        stmt = select(Account).where(Account.id == account_id, Account.entity_is_not_deleted())
        return (await self._session.scalars(stmt)).unique().one_or_none()

    async def get_active_by_email(self, email: str) -> Account | None:
        stmt = select(Account).where(Account.email == email, Account.entity_is_not_deleted())
        return (await self._session.scalars(stmt)).unique().one_or_none()

    async def get_active_by_phone(self, phone: str) -> Account | None:
        stmt = select(Account).where(Account.phone == phone, Account.entity_is_not_deleted())
        return (await self._session.scalars(stmt)).unique().one_or_none()

    async def list_active_by_emails(self, emails: Collection[str]) -> Sequence[Account]:
        stmt = select(Account).where(Account.email.in_(emails), Account.entity_is_not_deleted())
        return (await self._session.scalars(stmt)).unique().all()

    async def login_taken(
        self,
        email: str | None,
        phone: str | None,
        exclude_id: UUID | None = None,
    ) -> bool:
        conditions = []
        if email is not None:
            conditions.append(Account.email == email)
        if phone is not None:
            conditions.append(Account.phone == phone)
        if not conditions:
            return False
        stmt = select(Account.id).where(Account.entity_is_not_deleted())
        stmt = stmt.where(conditions[0] if len(conditions) == 1 else conditions[0] | conditions[1])
        if exclude_id is not None:
            stmt = stmt.where(Account.id != exclude_id)
        return (await self._session.scalar(select(exists(stmt)))) or False

    def add(self, account: Account) -> None:
        self._session.add(account)


class RoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, access: AccessContext) -> Sequence[Role]:
        stmt = apply_access_context(select(Role), Role, access).order_by(Role.name)
        return (await self._session.scalars(stmt)).all()

    async def get(self, access: AccessContext, role_id: UUID) -> Role | None:
        stmt = apply_access_context(select(Role).where(Role.id == role_id), Role, access)
        return (await self._session.scalars(stmt)).one_or_none()

    async def get_by_id(self, role_id: UUID) -> Role | None:
        return await self._session.get(Role, role_id)

    async def get_by_name(self, name: str) -> Role | None:
        return (await self._session.scalars(select(Role).where(Role.name == name))).one_or_none()

    async def is_in_use(self, role_id: UUID) -> bool:
        stmt = select(func.count()).select_from(Account).where(Account.role_id == role_id)
        return bool(await self._session.scalar(stmt))

    def add(self, role: Role) -> None:
        self._session.add(role)

    async def delete(self, role: Role) -> None:
        await self._session.delete(role)
