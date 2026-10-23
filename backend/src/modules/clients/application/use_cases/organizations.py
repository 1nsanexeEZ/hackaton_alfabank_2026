"""The company card: a client sees the companies they are a member of, the
bank — all of them."""

from uuid import UUID

from src.core.access.access_context import AccessContext
from src.core.domain.clock import Clock
from src.modules.clients.application.dto.organizations import OrganizationCardDTO
from src.modules.clients.application.interfaces.repositories import OrganizationRepository
from src.modules.clients.application.use_cases.common import get_organization


class ListOrganizationsUseCase:
    def __init__(self, organizations: OrganizationRepository, clock: Clock) -> None:
        self._organizations = organizations
        self._clock = clock

    async def execute(self, access: AccessContext) -> list[OrganizationCardDTO]:
        now = self._clock.now()
        return [
            OrganizationCardDTO.of(org, access.user_id, now)
            for org in await self._organizations.list_visible(access)
        ]


class GetOrganizationUseCase:
    def __init__(self, organizations: OrganizationRepository, clock: Clock) -> None:
        self._organizations = organizations
        self._clock = clock

    async def execute(self, access: AccessContext, organization_id: UUID) -> OrganizationCardDTO:
        org = await get_organization(self._organizations, organization_id, access)
        return OrganizationCardDTO.of(org, access.user_id, self._clock.now())
