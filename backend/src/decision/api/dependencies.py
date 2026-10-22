from uuid import UUID

from src.clients.facade import ClientsFacade, OrgPermission
from src.core.access.permissions import Permissions
from src.core.access.policies import Policies
from src.core.exceptions.exceptions import NotFoundError, PermissionDeniedError
from src.core.schemas.jwt_dto import OpenSubTokenDTO


def sees_every_organization(token: OpenSubTokenDTO) -> bool:
    """Admin and bank staff: `organizations.read` without the `org_member` policy."""
    if Permissions.ADMIN.value in token.permissions:
        return True
    permission = Permissions.ORGANIZATIONS_READ.value
    return permission in token.permissions and Policies.ORG_MEMBER.value not in (
        token.policies.get(permission, ())
    )


async def ensure_can_view(
    token: OpenSubTokenDTO, organization_id: UUID, clients: ClientsFacade
) -> None:
    """A client sees only its companies; a stranger gets 404, not 403."""
    if sees_every_organization(token):
        return
    try:
        await clients.ensure_can(token.subject, organization_id, OrgPermission.VIEW)
    except PermissionDeniedError:
        raise NotFoundError("Organization not found") from None
