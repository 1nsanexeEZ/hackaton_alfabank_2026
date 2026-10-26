from uuid import UUID

from src.modules.clients.facade import ClientsFacade, OrgPermission
from src.modules.notifications.application.interfaces.access import OrganizationAccess
from src.modules.notifications.application.interfaces.neighbours import FacadeLookup


class ClientsOrganizationAccess(OrganizationAccess):
    """The clients facade is looked up on a call, not when the adapter is built:
    a read by bank staff does not need it."""

    def __init__(self, facades: FacadeLookup) -> None:
        self._facades = facades

    async def ensure_can_view(self, account_id: UUID, organization_id: UUID) -> None:
        clients = self._facades(ClientsFacade)  # type: ignore[type-abstract]
        await clients.ensure_can(account_id, organization_id, OrgPermission.VIEW)

    async def member_organizations(self, account_id: UUID) -> frozenset[UUID]:
        clients = self._facades(ClientsFacade)  # type: ignore[type-abstract]
        return await clients.get_member_organization_ids(account_id)
