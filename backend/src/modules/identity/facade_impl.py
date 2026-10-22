from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.facade import AccountRefDTO
from src.modules.identity.models import Account
from src.modules.identity.passwords import PasswordHasher
from src.modules.identity.repositories import AccountRepository
from src.modules.identity.services import find_active_by_login


class IdentityFacadeImpl:
    """IdentityFacade for other modules. Deleted accounts are invisible:
    lookups return None, a password check fails."""

    def __init__(self, session: AsyncSession, hasher: PasswordHasher) -> None:
        self._accounts = AccountRepository(session)
        self._hasher = hasher

    async def get_account(self, account_id: UUID) -> AccountRefDTO | None:
        account = await self._accounts.get_active_by_id(account_id)
        return None if account is None else _to_dto(account)

    async def find_by_login(self, login: str) -> AccountRefDTO | None:
        account = await find_active_by_login(self._accounts, login)
        return None if account is None else _to_dto(account)

    async def verify_password(self, account_id: UUID, password: str) -> bool:
        account = await self._accounts.get_active_by_id(account_id)
        if account is None:
            self._hasher.verify_dummy(password)
            return False
        return self._hasher.verify(account.password_hash, password)


def _to_dto(account: Account) -> AccountRefDTO:
    profile = account.profile
    return AccountRefDTO(
        id=account.id,
        email=account.email,
        phone=account.phone,
        role_name=account.role.name,
        last_name=profile.last_name,
        first_name=profile.first_name,
        middle_name=profile.middle_name,
        position=profile.position,
    )
