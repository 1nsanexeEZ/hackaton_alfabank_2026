"""Identity contract for other modules (implementation: identity owner)."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AccountRefDTO:
    id: UUID
    email: str | None
    phone: str | None
    role_name: str
    last_name: str
    first_name: str
    middle_name: str | None = None
    position: str | None = None


class IdentityFacade(Protocol):
    async def get_account(self, account_id: UUID) -> AccountRefDTO | None: ...

    async def find_by_login(self, login: str) -> AccountRefDTO | None:
        """Email or phone, normalized the same way as on login."""
        ...

    async def verify_password(self, account_id: UUID, password: str) -> bool:
        """Step-up check before signing."""
        ...
