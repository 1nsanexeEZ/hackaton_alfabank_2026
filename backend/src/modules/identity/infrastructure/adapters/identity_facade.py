from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.domain.clock import Clock
from src.modules.identity.application.interfaces.password_hasher import PasswordHasher
from src.modules.identity.application.use_cases.auth import find_active_by_login
from src.modules.identity.domain.account import Account
from src.modules.identity.domain.enums import ConsentType
from src.modules.identity.facade import AccountRefDTO, ConsentDTO, IdentityFacade
from src.modules.identity.infrastructure.repositories.account import SqlAlchemyAccountRepository
from src.modules.identity.infrastructure.repositories.consent import SqlAlchemyConsentRepository


class IdentityFacadeImpl(IdentityFacade):
    """IdentityFacade for other modules. Deleted accounts are invisible:
    lookups return None, a password check fails."""

    def __init__(self, session: AsyncSession, hasher: PasswordHasher, clock: Clock) -> None:
        self._accounts = SqlAlchemyAccountRepository(session)
        self._consents = SqlAlchemyConsentRepository(session)
        self._hasher = hasher
        self._clock = clock

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

    async def get_active_consent(self, account_id: UUID, type: ConsentType) -> ConsentDTO | None:
        if await self._accounts.get_active_by_id(account_id) is None:
            return None
        now = self._clock.now()
        for consent in await self._consents.list_not_revoked(account_id, type):
            if consent.is_active(now):
                return ConsentDTO(
                    account_id=consent.account_id,
                    type=type,
                    given_at=consent.given_at,
                    valid_until=consent.valid_until,
                    text_version=consent.text_version,
                )
        return None


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
