from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.access.access_context import AccessContext
from src.core.access.organizations import MemberOrganizationsResolver
from src.core.access.permission_check import ensure_permissions
from src.core.access.permissions import Permissions
from src.core.access.policies import Policies
from src.core.facades import get_facade_registry
from src.core.infrastructure.database.session import get_session
from src.core.schemas.jwt_dto import OpenSubTokenDTO
from src.core.security import bearer_security


def get_current_token(
    _: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_security)],
) -> OpenSubTokenDTO:
    """Port — must be overridden at application composition root with the real
    token-extraction dependency (e.g. identity's get_current_request_token).

    Use app.dependency_overrides[get_current_token] = <real_impl> in create_app().

    The Security parameter is declared only so OpenAPI/Swagger advertises the bearer
    scheme; the override replaces this dependency entirely at runtime.
    """
    raise NotImplementedError(
        "Dependency 'get_current_token' must be overridden at application composition root. "
        "Use app.dependency_overrides[get_current_token] = <real_impl> in create_app()."
    )


CurrentToken = Annotated[OpenSubTokenDTO, Depends(get_current_token)]


def get_current_user_id(token: CurrentToken) -> UUID:
    return token.subject


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]


def require_permissions(*required: Permissions) -> Callable[[OpenSubTokenDTO], OpenSubTokenDTO]:
    """
    Use:
        @router.get(
        "/accounts",
        dependencies=[Depends(require_permissions(Permissions.ACCOUNTS_READ))])
    or:
        token: Annotated[OpenSubTokenDTO, Depends(require_permissions(Permissions.ACCOUNTS_READ))]
    """

    def dependency(token: CurrentToken) -> OpenSubTokenDTO:
        ensure_permissions(token, *required)
        return token

    return dependency


def needs_organization_ids(token: OpenSubTokenDTO, permission: Permissions) -> bool:
    if Permissions.ADMIN.value in token.permissions:
        return False
    return Policies.ORG_MEMBER.value in token.policies.get(permission.value, ())


def get_access_context_for(
    permission: Permissions,
) -> Callable[..., Awaitable[AccessContext]]:
    """
    Use:
        access: Annotated[AccessContext, Depends(get_access_context_for(Permissions.ACCOUNTS_READ))]

    This is the single permission gate for the route: it checks that the
    caller holds `permission` (raising PermissionDeniedError otherwise) and
    builds the AccessContext the repository uses for row-level (ABAC)
    filtering. Don't pair it with a separate require_permissions dependency —
    that would just be the same check done twice.

    When the permission carries the `org_member` policy, the organizations of
    the user are resolved through MemberOrganizationsResolver (registered by
    the clients module), only then and only once per request.
    """

    async def dependency(
        request: Request,
        token: CurrentToken,
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> AccessContext:
        ensure_permissions(token, permission)

        organization_ids: frozenset[UUID] | None = None
        if needs_organization_ids(token, permission):
            resolver = get_facade_registry(request).get(MemberOrganizationsResolver, session)
            organization_ids = await resolver.member_organization_ids(token.subject)

        return AccessContext(
            user_id=token.subject,
            permission=permission,
            granted_permissions=token.permissions,
            policies=token.policies,
            organization_ids=organization_ids,
        )

    return dependency
