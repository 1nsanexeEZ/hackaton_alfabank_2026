from typing import Protocol
from uuid import UUID


class OrganizationAccess(Protocol):
    async def ensure_can_view(self, account_id: UUID, organization_id: UUID) -> None:
        """Raises PermissionDeniedError when the account may not see the company."""
        ...
