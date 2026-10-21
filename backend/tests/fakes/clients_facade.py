from uuid import UUID

from src.clients.facade import (
    MemberRole,
    OrganizationSnapshotDTO,
    OrganizationSummaryDTO,
    OrgPermission,
)
from src.core.exceptions.exceptions import NotFoundError, PermissionDeniedError

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": frozenset(OrgPermission),
    "director": frozenset(OrgPermission),
    "accountant": frozenset(
        {OrgPermission.VIEW, OrgPermission.SUBMIT_APPLICATION, OrgPermission.EDIT_FINANCIALS}
    ),
    "employee": frozenset({OrgPermission.VIEW}),
}


class FakeClientsFacade:
    """Also serves as MemberOrganizationsResolver for the org_member policy."""

    def __init__(self) -> None:
        self.organizations: dict[UUID, OrganizationSnapshotDTO] = {}
        self.members: dict[tuple[UUID, UUID], tuple[MemberRole, frozenset[str]]] = {}

    def add_organization(self, snapshot: OrganizationSnapshotDTO) -> OrganizationSnapshotDTO:
        self.organizations[snapshot.id] = snapshot
        return snapshot

    def add_member(
        self,
        account_id: UUID,
        organization_id: UUID,
        role: MemberRole = "director",
        permissions: frozenset[str] | None = None,
    ) -> None:
        granted = ROLE_PERMISSIONS[role] if permissions is None else permissions
        self.members[(account_id, organization_id)] = (role, frozenset(str(p) for p in granted))

    async def ensure_can(self, account_id: UUID, organization_id: UUID, permission: str) -> None:
        member = self.members.get((account_id, organization_id))
        if member is None:
            raise NotFoundError("Organization not found")
        if str(permission) not in member[1]:
            raise PermissionDeniedError()

    async def get_member_permissions(
        self, account_id: UUID, organization_id: UUID
    ) -> frozenset[str]:
        member = self.members.get((account_id, organization_id))
        return member[1] if member else frozenset()

    async def get_member_organization_ids(self, account_id: UUID) -> frozenset[UUID]:
        return frozenset(org for (acc, org) in self.members if acc == account_id)

    async def member_organization_ids(self, account_id: UUID) -> frozenset[UUID]:
        return await self.get_member_organization_ids(account_id)

    async def get_snapshot(self, organization_id: UUID) -> OrganizationSnapshotDTO:
        try:
            return self.organizations[organization_id]
        except KeyError:
            raise NotFoundError("Organization not found") from None

    async def list_my_organizations(self, account_id: UUID) -> list[OrganizationSummaryDTO]:
        result = []
        for (acc, org_id), (role, permissions) in self.members.items():
            if acc != account_id or org_id not in self.organizations:
                continue
            org = self.organizations[org_id]
            result.append(
                OrganizationSummaryDTO(
                    id=org.id,
                    name=org.name,
                    inn=org.inn,
                    legal_form=org.legal_form,
                    my_role=role,
                    my_permissions=permissions,
                )
            )
        return result

    async def list_members(
        self, organization_id: UUID, permission: str | None = None
    ) -> list[UUID]:
        return [
            acc
            for (acc, org), (_, permissions) in self.members.items()
            if org == organization_id and (permission is None or str(permission) in permissions)
        ]
