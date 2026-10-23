from datetime import date
from typing import Annotated

from fastapi import Depends, Request

from src.core.access.access_context import AccessContext
from src.core.access.dependencies import get_access_context_for
from src.core.access.permissions import Permissions
from src.core.facades import get_facade_registry
from src.core.infrastructure.database.session import DbSession
from src.modules.bff.application.backoffice_screens import BackofficeScreens
from src.modules.bff.application.client_screens import ClientScreens
from src.modules.bff.application.neighbours import Neighbours


def get_neighbours(request: Request, session: DbSession) -> Neighbours:
    registry = get_facade_registry(request)
    return Neighbours(lambda key: registry.get(key, session))


def get_client_screens(neighbours: Annotated[Neighbours, Depends(get_neighbours)]) -> ClientScreens:
    return ClientScreens(neighbours)


def get_backoffice_screens(
    neighbours: Annotated[Neighbours, Depends(get_neighbours)],
) -> BackofficeScreens:
    return BackofficeScreens(neighbours)


def get_today(request: Request) -> date:
    return request.app.state.clock.now().date()  # type: ignore[no-any-return]


ClientScreensDep = Annotated[ClientScreens, Depends(get_client_screens)]
BackofficeScreensDep = Annotated[BackofficeScreens, Depends(get_backoffice_screens)]
Today = Annotated[date, Depends(get_today)]

# Clients get these with the `org_member` policy: organization_ids is the list
# of their companies; rights inside the company are checked by clients.ensure_can.
CanReadOrganizations = Annotated[
    AccessContext, Depends(get_access_context_for(Permissions.ORGANIZATIONS_READ))
]
CanReadApplications = Annotated[
    AccessContext, Depends(get_access_context_for(Permissions.REQUESTS_READ))
]
CanReadProducts = Annotated[
    AccessContext, Depends(get_access_context_for(Permissions.CREDITS_READ))
]
# Bank staff only.
CanReadBackoffice = Annotated[
    AccessContext, Depends(get_access_context_for(Permissions.BACKOFFICE_READ))
]
