from typing import Protocol
from uuid import UUID


class MemberOrganizationsResolver(Protocol):
    """Port for the `org_member` policy: which organizations an account is a member of.

    Core can't know about client organizations, so the clients module registers
    the implementation in the facade registry (`app.state.facades`) under this type.
    """

    async def member_organization_ids(self, account_id: UUID) -> frozenset[UUID]: ...
