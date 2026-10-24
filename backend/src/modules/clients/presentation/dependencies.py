"""Use cases for the routers, the Kafka handler and the facade: adapters are
picked here, use cases see only interfaces."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.access.access_context import AccessContext
from src.core.access.dependencies import get_access_context_for
from src.core.access.permissions import Permissions
from src.core.domain.clock import Clock
from src.core.facades import use_facade
from src.core.infrastructure.database.session import DbSession
from src.core.messaging.outbox import SqlAlchemyOutboxWriter
from src.core.messaging.subscriber import HandlerContext
from src.core.uow import SqlAlchemyUnitOfWork, UnitOfWork
from src.modules.clients.application.interfaces.outbox import EventOutbox
from src.modules.clients.application.interfaces.repositories import (
    BusinessPlanRepository,
    FinancialReportRepository,
    OrganizationRepository,
)
from src.modules.clients.application.mappers.events import PRODUCER
from src.modules.clients.application.use_cases.business_plan import (
    FindBusinessPlanUseCase,
    GetBusinessPlanUseCase,
    SubmitBusinessPlanUseCase,
)
from src.modules.clients.application.use_cases.inn_check import CheckInnUseCase
from src.modules.clients.application.use_cases.members import (
    AddMemberUseCase,
    ChangeMemberRoleUseCase,
    GrantPowerOfAttorneyUseCase,
    ListMembersUseCase,
    RemoveMemberUseCase,
)
from src.modules.clients.application.use_cases.membership import (
    EnsureCanUseCase,
    GetMemberOrganizationIdsUseCase,
    GetMemberPermissionsUseCase,
    GetRegistryHeadUseCase,
    ListMemberIdsUseCase,
    ListMyOrganizationsUseCase,
)
from src.modules.clients.application.use_cases.organizations import (
    GetOrganizationUseCase,
    ListOrganizationsUseCase,
)
from src.modules.clients.application.use_cases.reports import (
    ListFinancialReportsUseCase,
    SubmitFinancialReportUseCase,
)
from src.modules.clients.application.use_cases.snapshot import GetSnapshotUseCase
from src.modules.clients.application.use_cases.verification import (
    ApplyRegistryExtractUseCase,
    VerifyOrganizationUseCase,
)
from src.modules.clients.infrastructure.adapters.clients_facade import ClientsFacadeImpl
from src.modules.clients.infrastructure.adapters.enrichment_company_check import (
    EnrichmentCompanyCheck,
)
from src.modules.clients.infrastructure.adapters.enrichment_registry import (
    EnrichmentRegistryLookup,
)
from src.modules.clients.infrastructure.repositories.business_plan import (
    SqlAlchemyBusinessPlanRepository,
)
from src.modules.clients.infrastructure.repositories.financial_report import (
    SqlAlchemyFinancialReportRepository,
)
from src.modules.clients.infrastructure.repositories.organization import (
    SqlAlchemyOrganizationRepository,
)
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.identity.facade import IdentityFacade

# --- facade --------------------------------------------------------------------


def clients_facade(session: AsyncSession, clock: Clock) -> ClientsFacadeImpl:
    organizations = SqlAlchemyOrganizationRepository(session)
    return ClientsFacadeImpl(
        EnsureCanUseCase(organizations, clock),
        GetMemberPermissionsUseCase(organizations, clock),
        GetMemberOrganizationIdsUseCase(organizations),
        GetSnapshotUseCase(organizations, SqlAlchemyFinancialReportRepository(session), clock),
        ListMyOrganizationsUseCase(organizations, clock),
        ListMemberIdsUseCase(organizations, clock),
        GetRegistryHeadUseCase(organizations),
        FindBusinessPlanUseCase(SqlAlchemyBusinessPlanRepository(session)),
    )


# --- Kafka ---------------------------------------------------------------------


def apply_registry_extract_use_case(ctx: HandlerContext) -> ApplyRegistryExtractUseCase:
    """The handler's transaction is committed by the core with the inbox."""
    return ApplyRegistryExtractUseCase(
        SqlAlchemyOrganizationRepository(ctx.session),
        ctx.outbox,
        ctx.clock,
        EnrichmentRegistryLookup(ctx.facade(EnrichmentFacade)),  # type: ignore[type-abstract]
        ctx.facade(IdentityFacade),  # type: ignore[type-abstract]
    )


# --- adapters for the routers --------------------------------------------------


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


def get_uow(session: DbSession) -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session)


def get_organization_repository(session: DbSession) -> OrganizationRepository:
    return SqlAlchemyOrganizationRepository(session)


def get_report_repository(session: DbSession) -> FinancialReportRepository:
    return SqlAlchemyFinancialReportRepository(session)


def get_business_plan_repository(session: DbSession) -> BusinessPlanRepository:
    return SqlAlchemyBusinessPlanRepository(session)


def get_outbox(request: Request, session: DbSession) -> EventOutbox:
    return SqlAlchemyOutboxWriter(session, PRODUCER, request.app.state.clock)


ClockDep = Annotated[Clock, Depends(get_clock)]
Uow = Annotated[UnitOfWork, Depends(get_uow)]
Organizations = Annotated[OrganizationRepository, Depends(get_organization_repository)]
Reports = Annotated[FinancialReportRepository, Depends(get_report_repository)]
Plans = Annotated[BusinessPlanRepository, Depends(get_business_plan_repository)]
Outbox = Annotated[EventOutbox, Depends(get_outbox)]
IdentityDep = Annotated[IdentityFacade, Depends(use_facade(IdentityFacade))]
EnrichmentDep = Annotated[EnrichmentFacade, Depends(use_facade(EnrichmentFacade))]
ReadAccess = Annotated[
    AccessContext, Depends(get_access_context_for(Permissions.ORGANIZATIONS_READ))
]
UpdateAccess = Annotated[
    AccessContext, Depends(get_access_context_for(Permissions.ORGANIZATIONS_UPDATE))
]
# Bank staff only: the check by INN before an application.
BackofficeAccess = Annotated[
    AccessContext, Depends(get_access_context_for(Permissions.BACKOFFICE_READ))
]


# --- organizations -------------------------------------------------------------


def get_list_organizations(
    organizations: Organizations, clock: ClockDep
) -> ListOrganizationsUseCase:
    return ListOrganizationsUseCase(organizations, clock)


def get_get_organization(organizations: Organizations, clock: ClockDep) -> GetOrganizationUseCase:
    return GetOrganizationUseCase(organizations, clock)


def get_verify_organization(
    uow: Uow,
    organizations: Organizations,
    outbox: Outbox,
    clock: ClockDep,
    identity: IdentityDep,
    enrichment: EnrichmentDep,
) -> VerifyOrganizationUseCase:
    return VerifyOrganizationUseCase(
        uow, organizations, outbox, clock, EnrichmentRegistryLookup(enrichment), identity
    )


def get_check_inn(
    organizations: Organizations, clock: ClockDep, enrichment: EnrichmentDep
) -> CheckInnUseCase:
    return CheckInnUseCase(EnrichmentCompanyCheck(enrichment), organizations, clock)


# --- members -------------------------------------------------------------------


def get_list_members(
    organizations: Organizations, identity: IdentityDep, clock: ClockDep
) -> ListMembersUseCase:
    return ListMembersUseCase(organizations, identity, clock)


def get_add_member(
    uow: Uow, organizations: Organizations, outbox: Outbox, identity: IdentityDep, clock: ClockDep
) -> AddMemberUseCase:
    return AddMemberUseCase(uow, organizations, outbox, identity, clock)


def get_change_member_role(
    uow: Uow, organizations: Organizations, outbox: Outbox, clock: ClockDep
) -> ChangeMemberRoleUseCase:
    return ChangeMemberRoleUseCase(uow, organizations, outbox, clock)


def get_remove_member(
    uow: Uow, organizations: Organizations, outbox: Outbox, clock: ClockDep
) -> RemoveMemberUseCase:
    return RemoveMemberUseCase(uow, organizations, outbox, clock)


def get_grant_power_of_attorney(
    uow: Uow, organizations: Organizations, outbox: Outbox, clock: ClockDep
) -> GrantPowerOfAttorneyUseCase:
    return GrantPowerOfAttorneyUseCase(uow, organizations, outbox, clock)


# --- financial reports ---------------------------------------------------------


def get_list_financial_reports(
    organizations: Organizations, reports: Reports
) -> ListFinancialReportsUseCase:
    return ListFinancialReportsUseCase(organizations, reports)


def get_submit_financial_report(
    uow: Uow, organizations: Organizations, reports: Reports, outbox: Outbox, clock: ClockDep
) -> SubmitFinancialReportUseCase:
    return SubmitFinancialReportUseCase(uow, organizations, reports, outbox, clock)


# --- business plan -------------------------------------------------------------


def get_get_business_plan(organizations: Organizations, plans: Plans) -> GetBusinessPlanUseCase:
    return GetBusinessPlanUseCase(organizations, plans)


def get_submit_business_plan(
    uow: Uow, organizations: Organizations, plans: Plans, clock: ClockDep
) -> SubmitBusinessPlanUseCase:
    return SubmitBusinessPlanUseCase(uow, organizations, plans, clock)


ListOrganizationsDep = Annotated[ListOrganizationsUseCase, Depends(get_list_organizations)]
GetOrganizationDep = Annotated[GetOrganizationUseCase, Depends(get_get_organization)]
VerifyOrganizationDep = Annotated[VerifyOrganizationUseCase, Depends(get_verify_organization)]
CheckInnDep = Annotated[CheckInnUseCase, Depends(get_check_inn)]
ListMembersDep = Annotated[ListMembersUseCase, Depends(get_list_members)]
AddMemberDep = Annotated[AddMemberUseCase, Depends(get_add_member)]
ChangeMemberRoleDep = Annotated[ChangeMemberRoleUseCase, Depends(get_change_member_role)]
RemoveMemberDep = Annotated[RemoveMemberUseCase, Depends(get_remove_member)]
GrantPowerOfAttorneyDep = Annotated[
    GrantPowerOfAttorneyUseCase, Depends(get_grant_power_of_attorney)
]
ListFinancialReportsDep = Annotated[
    ListFinancialReportsUseCase, Depends(get_list_financial_reports)
]
SubmitFinancialReportDep = Annotated[
    SubmitFinancialReportUseCase, Depends(get_submit_financial_report)
]
GetBusinessPlanDep = Annotated[GetBusinessPlanUseCase, Depends(get_get_business_plan)]
SubmitBusinessPlanDep = Annotated[SubmitBusinessPlanUseCase, Depends(get_submit_business_plan)]
