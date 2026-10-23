"""Who is a member of which company and what they may do there: reads for the
facade and the `org_member` policy. Rights are computed at the clock's `now`."""

from uuid import UUID

from src.core.domain.clock import Clock
from src.modules.clients.application.dto.membership import OrganizationSummaryDTO
from src.modules.clients.application.interfaces.repositories import OrganizationRepository
from src.modules.clients.application.use_cases.common import get_organization
from src.modules.clients.domain.enums import Authority, MemberRole, OrgPermission
from src.modules.clients.domain.rights import HEAD_ROLES


def _permission(value: str) -> OrgPermission:
    try:
        return OrgPermission(str(value))
    except ValueError:
        raise ValueError(f"Unknown organization permission {value!r}") from None


def _names(permissions: frozenset[OrgPermission]) -> frozenset[str]:
    return frozenset(p.value for p in permissions)


class EnsureCanUseCase:
    def __init__(self, organizations: OrganizationRepository, clock: Clock) -> None:
        self._organizations = organizations
        self._clock = clock

    async def execute(self, account_id: UUID, organization_id: UUID, permission: str) -> None:
        """PermissionDeniedError; a stranger to the company gets NotFoundError,
        an unknown permission — ValueError."""
        org = await get_organization(self._organizations, organization_id)
        org.ensure_can(account_id, _permission(permission), self._clock.now())


class GetMemberPermissionsUseCase:
    def __init__(self, organizations: OrganizationRepository, clock: Clock) -> None:
        self._organizations = organizations
        self._clock = clock

    async def execute(self, account_id: UUID, organization_id: UUID) -> frozenset[str]:
        org = await self._organizations.get(organization_id)
        if org is None:
            return frozenset()
        return _names(org.permissions_of(account_id, self._clock.now()))


class GetMemberOrganizationIdsUseCase:
    def __init__(self, organizations: OrganizationRepository) -> None:
        self._organizations = organizations

    async def execute(self, account_id: UUID) -> frozenset[UUID]:
        return await self._organizations.member_organization_ids(account_id)


class ListMyOrganizationsUseCase:
    def __init__(self, organizations: OrganizationRepository, clock: Clock) -> None:
        self._organizations = organizations
        self._clock = clock

    async def execute(self, account_id: UUID) -> list[OrganizationSummaryDTO]:
        now = self._clock.now()
        return [
            OrganizationSummaryDTO(
                id=org.id,
                name=org.name,
                inn=org.requisites.inn.value,
                legal_form=org.legal_form.value,  # type: ignore[arg-type]
                my_role=org.member(account_id).role.value,  # type: ignore[arg-type]
                my_permissions=_names(org.permissions_of(account_id, now)),
            )
            for org in await self._organizations.list_for_member(account_id)
        ]


class ListMemberIdsUseCase:
    def __init__(self, organizations: OrganizationRepository, clock: Clock) -> None:
        self._organizations = organizations
        self._clock = clock

    async def execute(self, organization_id: UUID, permission: str | None = None) -> list[UUID]:
        """Members holding `permission` now; None — every member."""
        org = await self._organizations.get(organization_id)
        if org is None:
            return []
        wanted = _permission(permission) if permission is not None else None
        return org.members_with(wanted, self._clock.now())


class GetRegistryHeadUseCase:
    def __init__(self, organizations: OrganizationRepository) -> None:
        self._organizations = organizations

    async def execute(self, organization_id: UUID) -> UUID | None:
        """The member whose name matched the head in the registry; a director
        goes before an owner."""
        org = await self._organizations.get(organization_id)
        if org is None:
            return None
        heads = [
            m for m in org.members if m.role in HEAD_ROLES and m.authority is Authority.REGISTRY
        ]
        if not heads:
            return None
        heads.sort(key=lambda m: (m.role is not MemberRole.DIRECTOR, m.added_at))
        return heads[0].account_id
