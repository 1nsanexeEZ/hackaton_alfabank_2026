from uuid import UUID

from src.core.access.access_context import AccessContext
from src.core.domain.clock import Clock
from src.core.uow import UnitOfWork
from src.modules.identity.application.dto.accounts import (
    AccountDTO,
    CreateAccountDTO,
    UpdateAccountDTO,
)
from src.modules.identity.application.dto.common import UNSET
from src.modules.identity.application.interfaces.password_hasher import PasswordHasher
from src.modules.identity.application.interfaces.repositories import (
    AccountRepository,
    RoleRepository,
)
from src.modules.identity.domain.account import Account
from src.modules.identity.domain.entities import Role
from src.modules.identity.domain.exceptions import (
    AccountNotFoundError,
    LoginTakenError,
    SelfDeletionError,
    UnknownRoleError,
)


async def _get_account(
    accounts: AccountRepository, access: AccessContext, account_id: UUID
) -> Account:
    account = await accounts.get(access, account_id)
    if account is None:
        raise AccountNotFoundError()
    return account


async def _role_for_account(roles: RoleRepository, role_id: UUID) -> Role:
    role = await roles.get_by_id(role_id)
    if role is None:
        raise UnknownRoleError()
    return role


class ListAccountsUseCase:
    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts

    async def execute(self, access: AccessContext, limit: int, offset: int) -> list[AccountDTO]:
        return [
            AccountDTO.from_entity(account)
            for account in await self._accounts.list(access, limit, offset)
        ]


class GetAccountUseCase:
    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts

    async def execute(self, access: AccessContext, account_id: UUID) -> AccountDTO:
        return AccountDTO.from_entity(await _get_account(self._accounts, access, account_id))


class CreateAccountUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        accounts: AccountRepository,
        roles: RoleRepository,
        hasher: PasswordHasher,
    ) -> None:
        self._uow = uow
        self._accounts = accounts
        self._roles = roles
        self._hasher = hasher

    async def execute(self, data: CreateAccountDTO) -> AccountDTO:
        async with self._uow:
            role = await _role_for_account(self._roles, data.role_id)
            if await self._accounts.login_taken(data.email, data.phone):
                raise LoginTakenError()
            account = Account.register(
                email=data.email,
                phone=data.phone,
                password_hash=self._hasher.hash(data.password),
                role=role,
                profile=data.profile.to_entity(),
            )
            await self._accounts.add(account)
            await self._uow.commit()
        return AccountDTO.from_entity(account)


class UpdateAccountUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        accounts: AccountRepository,
        roles: RoleRepository,
        hasher: PasswordHasher,
    ) -> None:
        self._uow = uow
        self._accounts = accounts
        self._roles = roles
        self._hasher = hasher

    async def execute(
        self, access: AccessContext, account_id: UUID, data: UpdateAccountDTO
    ) -> AccountDTO:
        async with self._uow:
            account = await _get_account(self._accounts, access, account_id)
            if account.is_deleted:
                raise AccountNotFoundError()

            if data.email is not UNSET or data.phone is not UNSET:
                new_email = None if data.email is UNSET else data.email
                new_phone = None if data.phone is UNSET else data.phone
                if await self._accounts.login_taken(new_email, new_phone, exclude_id=account.id):
                    raise LoginTakenError()
                account.change_login(
                    account.email if data.email is UNSET else data.email,
                    account.phone if data.phone is UNSET else data.phone,
                )
            if data.role_id is not None:
                account.assign_role(await _role_for_account(self._roles, data.role_id))
            if data.password is not None:
                account.set_password_hash(self._hasher.hash(data.password))
            if data.profile is not None:
                account.profile.apply_changes(data.profile.changes())

            await self._accounts.save(account)
            await self._uow.commit()
        return AccountDTO.from_entity(account)


class DeleteAccountUseCase:
    """Soft delete: the account can't log in and disappears for roles with `not_deleted`."""

    def __init__(self, uow: UnitOfWork, accounts: AccountRepository, clock: Clock) -> None:
        self._uow = uow
        self._accounts = accounts
        self._clock = clock

    async def execute(self, access: AccessContext, account_id: UUID) -> None:
        async with self._uow:
            account = await _get_account(self._accounts, access, account_id)
            if account.id == access.user_id:
                raise SelfDeletionError()
            if not account.is_deleted:
                account.mark_deleted(self._clock.now())
                await self._accounts.save(account)
                await self._uow.commit()
