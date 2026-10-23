"""Identity contract for other modules (implementation: identity owner)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.modules.identity.domain.enums import (
    CompanyConsentType,
    ConsentType,
    PersonalConsentType,
)

__all__ = [
    "AccountRefDTO",
    "CompanyConsentType",
    "ConsentDTO",
    "ConsentType",
    "IdentityFacade",
    "PersonalConsentType",
]


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


@dataclass(frozen=True, slots=True)
class ConsentDTO:
    # Who gave it: the person themselves or, for a company consent, the representative.
    account_id: UUID
    type: ConsentType
    given_at: datetime
    valid_until: datetime | None
    text_version: str
    # Set for a company consent only.
    organization_id: UUID | None = None


class IdentityFacade(Protocol):
    async def get_account(self, account_id: UUID) -> AccountRefDTO | None: ...

    async def find_by_login(self, login: str) -> AccountRefDTO | None:
        """Email or phone, normalized the same way as on login."""
        ...

    async def verify_password(self, account_id: UUID, password: str) -> bool:
        """Step-up check before signing."""
        ...

    async def get_active_consent(
        self, account_id: UUID, type: PersonalConsentType
    ) -> ConsentDTO | None:
        """The person's latest consent of this type if it is in force now: not revoked,
        not expired. None — no consent, it was revoked or it ran out."""
        ...

    async def get_active_organization_consent(
        self, organization_id: UUID, type: CompanyConsentType
    ) -> ConsentDTO | None:
        """The company's latest consent of this type in force now, whichever representative
        gave it. None — no consent, it was revoked or it ran out."""
        ...
