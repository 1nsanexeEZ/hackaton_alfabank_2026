from uuid import UUID

from src.core.uow import UnitOfWork
from src.modules.identity.application.dto.accounts import AccountDTO, ProfileChangesDTO
from src.modules.identity.application.interfaces.repositories import AccountRepository
from src.modules.identity.domain.account import Account
from src.modules.identity.domain.exceptions import CurrentAccountNotFoundError


async def get_current_account(accounts: AccountRepository, user_id: UUID) -> Account:
    """The token's own account; gone if deleted after the token was issued."""
    account = await accounts.get_active_by_id(user_id)
    if account is None:
        raise CurrentAccountNotFoundError()
    return account


class GetMeUseCase:
    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts

    async def execute(self, user_id: UUID) -> AccountDTO:
        return AccountDTO.from_entity(await get_current_account(self._accounts, user_id))


class UpdateMyProfileUseCase:
    def __init__(self, uow: UnitOfWork, accounts: AccountRepository) -> None:
        self._uow = uow
        self._accounts = accounts

    async def execute(self, user_id: UUID, data: ProfileChangesDTO) -> AccountDTO:
        async with self._uow:
            account = await get_current_account(self._accounts, user_id)
            account.profile.apply_changes(data.changes())
            await self._accounts.save(account)
            await self._uow.commit()
        return AccountDTO.from_entity(account)
