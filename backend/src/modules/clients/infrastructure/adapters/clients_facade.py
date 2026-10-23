"""ClientsFacade for other modules; also the MemberOrganizationsResolver port
of the `org_member` policy. Only calls the use cases, no logic of its own.
Built per session: reads join the caller's transaction."""

from uuid import UUID

from src.core.access.organizations import MemberOrganizationsResolver
from src.modules.clients.application.dto.membership import OrganizationSummaryDTO
from src.modules.clients.application.dto.snapshot import OrganizationSnapshotDTO
from src.modules.clients.application.use_cases.membership import (
    EnsureCanUseCase,
    GetMemberOrganizationIdsUseCase,
    GetMemberPermissionsUseCase,
    GetRegistryHeadUseCase,
    ListMemberIdsUseCase,
    ListMyOrganizationsUseCase,
)
from src.modules.clients.application.use_cases.snapshot import GetSnapshotUseCase
from src.modules.clients.facade import ClientsFacade


class ClientsFacadeImpl(ClientsFacade, MemberOrganizationsResolver):
    def __init__(
        self,
        ensure_can: EnsureCanUseCase,
        get_member_permissions: GetMemberPermissionsUseCase,
        get_member_organization_ids: GetMemberOrganizationIdsUseCase,
        get_snapshot: GetSnapshotUseCase,
        list_my_organizations: ListMyOrganizationsUseCase,
        list_members: ListMemberIdsUseCase,
        get_registry_head: GetRegistryHeadUseCase,
    ) -> None:
        self._ensure_can = ensure_can
        self._get_member_permissions = get_member_permissions
        self._get_member_organization_ids = get_member_organization_ids
        self._get_snapshot = get_snapshot
        self._list_my_organizations = list_my_organizations
        self._list_members = list_members
        self._get_registry_head = get_registry_head

    async def ensure_can(self, account_id: UUID, organization_id: UUID, permission: str) -> None:
        await self._ensure_can.execute(account_id, organization_id, permission)

    async def get_member_permissions(
        self, account_id: UUID, organization_id: UUID
    ) -> frozenset[str]:
        return await self._get_member_permissions.execute(account_id, organization_id)

    async def get_member_organization_ids(self, account_id: UUID) -> frozenset[UUID]:
        return await self._get_member_organization_ids.execute(account_id)

    async def member_organization_ids(self, account_id: UUID) -> frozenset[UUID]:
        """MemberOrganizationsResolver: companies where the account is a member."""
        return await self._get_member_organization_ids.execute(account_id)

    async def get_snapshot(self, organization_id: UUID) -> OrganizationSnapshotDTO:
        return await self._get_snapshot.execute(organization_id)

    async def list_my_organizations(self, account_id: UUID) -> list[OrganizationSummaryDTO]:
        return await self._list_my_organizations.execute(account_id)

    async def list_members(
        self, organization_id: UUID, permission: str | None = None
    ) -> list[UUID]:
        return await self._list_members.execute(organization_id, permission)

    async def get_registry_head(self, organization_id: UUID) -> UUID | None:
        return await self._get_registry_head.execute(organization_id)
