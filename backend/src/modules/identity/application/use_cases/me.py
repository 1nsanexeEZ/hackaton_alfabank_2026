from uuid import UUID

from src.core.uow import UnitOfWork
from src.modules.identity.application.dto.accounts import AccountDTO, ProfileChangesDTO
from src.modules.identity.application.interfaces.repositories import AccountRepository
from src.modules.identity.domain.account import Account
from src.modules.identity.domain.exceptions import CurrentAccountNotFoundError, NameLockedError


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


NAME_FIELDS = ("last_name", "first_name", "middle_name")


class UpdateMyProfileUseCase:
    def __init__(self, uow: UnitOfWork, accounts: AccountRepository) -> None:
        self._uow = uow
        self._accounts = accounts

    async def execute(
        self, user_id: UUID, data: ProfileChangesDTO, *, may_change_name: bool
    ) -> AccountDTO:
        """`may_change_name` — the caller holds `profile.update_name`. Without it the
        name is locked; sending it unchanged is fine, a form may send every field."""
        async with self._uow:
            account = await get_current_account(self._accounts, user_id)
            changes = data.changes()
            if not may_change_name:
                renamed = [
                    field
                    for field in NAME_FIELDS
                    if field in changes and changes[field] != getattr(account.profile, field)
                ]
                if renamed:
                    raise NameLockedError(renamed)
            account.profile.apply_changes(changes)
            await self._accounts.save(account)
            await self._uow.commit()
        return AccountDTO.from_entity(account)
