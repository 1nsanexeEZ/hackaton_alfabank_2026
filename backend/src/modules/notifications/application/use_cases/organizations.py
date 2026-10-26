from uuid import UUID

from src.core.exceptions.exceptions import NotFoundError, PermissionDeniedError
from src.modules.notifications.application.interfaces.access import OrganizationAccess


class EnsureOrganizationVisibleUseCase:
    """A client filters the feed and the news only by its own companies; a
    stranger's company is 404. Bank staff may look at any company. The company
    is checked only when a filter is given."""

    def __init__(self, access: OrganizationAccess) -> None:
        self._access = access

    async def execute(
        self, account_id: UUID, bank_staff: bool, organization_id: UUID | None
    ) -> None:
        if organization_id is None or bank_staff:
            return
        try:
            await self._access.ensure_can_view(account_id, organization_id)
        except PermissionDeniedError:
            raise NotFoundError("Organization not found") from None


class ViewerOrganizationsUseCase:
    """The companies whose records a viewer reads in the feed: for a client, those
    where the account is a member now; for bank staff, any (None). The feed is
    copied to the members when an event happens, so a former member still holds
    the records of the company: this scope hides them."""

    def __init__(self, access: OrganizationAccess) -> None:
        self._access = access

    async def execute(self, account_id: UUID, bank_staff: bool) -> frozenset[UUID] | None:
        if bank_staff:
            return None
        return await self._access.member_organizations(account_id)
