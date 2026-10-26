"""What the use cases need from storage; implemented in infrastructure/repositories."""

from collections.abc import Collection, Sequence
from typing import Protocol
from uuid import UUID

from src.core.access.access_context import AccessContext
from src.modules.identity.domain.account import Account
from src.modules.identity.domain.entities import Consent, Role
from src.modules.identity.domain.enums import ConsentType
from src.modules.identity.domain.login_policy import Login


class AccountRepository(Protocol):
    """Methods taking an AccessContext are row-level filtered by the caller's
    policies. The rest are internal lookups (login, /me) and see every live account."""

    async def list(self, access: AccessContext, limit: int, offset: int) -> Sequence[Account]: ...

    async def count(self, access: AccessContext) -> int:
        """How many accounts `list` pages through."""
        ...

    async def get(self, access: AccessContext, account_id: UUID) -> Account | None: ...

    async def get_active_by_id(self, account_id: UUID) -> Account | None: ...

    async def get_active_by_login(self, login: Login) -> Account | None: ...

    async def list_active_by_emails(self, emails: Collection[str]) -> Sequence[Account]: ...

    async def login_taken(
        self,
        email: str | None,
        phone: str | None,
        exclude_id: UUID | None = None,
    ) -> bool:
        """Whether a live account (other than `exclude_id`) has this email or phone."""
        ...

    async def add(self, account: Account) -> None: ...

    async def save(self, account: Account) -> None: ...


class RoleRepository(Protocol):
    async def list(self, access: AccessContext) -> Sequence[Role]: ...

    async def get(self, access: AccessContext, role_id: UUID) -> Role | None: ...

    async def get_by_id(self, role_id: UUID) -> Role | None: ...

    async def get_by_name(self, name: str) -> Role | None: ...

    async def is_in_use(self, role_id: UUID) -> bool:
        """Whether any account, deleted ones included, has the role."""
        ...

    async def add(self, role: Role) -> None: ...

    async def save(self, role: Role) -> None: ...

    async def delete(self, role: Role) -> None: ...


class ConsentRepository(Protocol):
    async def list_for(self, account_id: UUID) -> Sequence[Consent]:
        """Every personal consent of the account, newest first."""
        ...

    async def list_not_revoked(self, account_id: UUID, type: ConsentType) -> Sequence[Consent]:
        """Personal consents of this type that were never revoked, newest first; some may
        have run out."""
        ...

    async def list_for_organization(self, organization_id: UUID) -> Sequence[Consent]:
        """Every consent given for the company, by any representative, newest first."""
        ...

    async def list_not_revoked_for_organization(
        self, organization_id: UUID, type: ConsentType
    ) -> Sequence[Consent]:
        """Company consents of this type that were never revoked, newest first."""
        ...

    async def add(self, consent: Consent) -> None: ...

    async def save(self, consent: Consent) -> None: ...
