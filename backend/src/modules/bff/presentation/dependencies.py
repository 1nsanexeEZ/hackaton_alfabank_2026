"""Assembly of the screen use cases from the facades of the neighbours."""

from typing import Annotated

from fastapi import Depends, Request

from src.core.access.access_context import AccessContext
from src.core.access.dependencies import get_access_context_for
from src.core.access.permissions import Permissions
from src.core.domain.clock import Clock
from src.core.facades import get_facade_registry
from src.core.infrastructure.database.session import DbSession
from src.modules.bff.application.interfaces.neighbours import Neighbours
from src.modules.bff.application.use_cases.applications import (
    ApplicationCardUseCase,
    ListApplicationsUseCase,
)
from src.modules.bff.application.use_cases.backoffice import (
    BackofficeMetricsUseCase,
    UnderwriterCardUseCase,
    UnderwritingQueueUseCase,
)
from src.modules.bff.application.use_cases.dashboard import DashboardUseCase
from src.modules.bff.application.use_cases.products import (
    PersonalScheduleUseCase,
    RecommendProductsUseCase,
)
from src.modules.bff.infrastructure.adapters.neighbours import FacadeNeighbours


def get_neighbours(request: Request, session: DbSession) -> Neighbours:
    return FacadeNeighbours(get_facade_registry(request), session)


def get_clock(request: Request) -> Clock:
    return request.app.state.clock  # type: ignore[no-any-return]


NeighboursDep = Annotated[Neighbours, Depends(get_neighbours)]


def get_dashboard(neighbours: NeighboursDep) -> DashboardUseCase:
    return DashboardUseCase(neighbours)


def get_list_applications(neighbours: NeighboursDep) -> ListApplicationsUseCase:
    return ListApplicationsUseCase(neighbours)


def get_application_card(neighbours: NeighboursDep) -> ApplicationCardUseCase:
    return ApplicationCardUseCase(neighbours)


def get_recommend_products(neighbours: NeighboursDep) -> RecommendProductsUseCase:
    return RecommendProductsUseCase(neighbours)


def get_personal_schedule(neighbours: NeighboursDep) -> PersonalScheduleUseCase:
    return PersonalScheduleUseCase(neighbours)


def get_underwriting_queue(neighbours: NeighboursDep) -> UnderwritingQueueUseCase:
    return UnderwritingQueueUseCase(neighbours)


def get_underwriter_card(neighbours: NeighboursDep) -> UnderwriterCardUseCase:
    return UnderwriterCardUseCase(neighbours)


def get_backoffice_metrics(
    neighbours: NeighboursDep, clock: Annotated[Clock, Depends(get_clock)]
) -> BackofficeMetricsUseCase:
    return BackofficeMetricsUseCase(neighbours, clock)


DashboardDep = Annotated[DashboardUseCase, Depends(get_dashboard)]
ListApplicationsDep = Annotated[ListApplicationsUseCase, Depends(get_list_applications)]
ApplicationCardDep = Annotated[ApplicationCardUseCase, Depends(get_application_card)]
RecommendProductsDep = Annotated[RecommendProductsUseCase, Depends(get_recommend_products)]
PersonalScheduleDep = Annotated[PersonalScheduleUseCase, Depends(get_personal_schedule)]
UnderwritingQueueDep = Annotated[UnderwritingQueueUseCase, Depends(get_underwriting_queue)]
UnderwriterCardDep = Annotated[UnderwriterCardUseCase, Depends(get_underwriter_card)]
BackofficeMetricsDep = Annotated[BackofficeMetricsUseCase, Depends(get_backoffice_metrics)]

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
