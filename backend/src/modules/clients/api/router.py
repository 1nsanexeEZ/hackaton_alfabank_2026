"""Companies of the client: card, members and their rights, financial reports.

`organizations.read` / `organizations.update` with the `org_member` policy:
somebody else's company is 404. Inside the company the rights table decides:
no `manage_members` / `edit_financials` — 403.
"""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Response, status

from src.core.domain import Money
from src.modules.clients.api.dependencies import IdentityDep, ReadAccess, ServiceDep, UpdateAccess
from src.modules.clients.api.schemas import (
    FinancialReportCreate,
    FinancialReportRead,
    MemberCreate,
    MemberRead,
    MemberUpdate,
    OrganizationRead,
    OrganizationSummaryRead,
    PowerOfAttorneyCreate,
)
from src.modules.clients.domain.financial_report import ReportFigures
from src.modules.clients.domain.rights import PowerOfAttorney
from src.modules.clients.domain.value_objects import FiscalPeriod

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _money(value: Decimal | None) -> Money | None:
    return Money(value) if value is not None else None


@router.get("", response_model=list[OrganizationSummaryRead])
async def list_organizations(
    access: ReadAccess, service: ServiceDep
) -> list[OrganizationSummaryRead]:
    """My companies with my role and rights; the bank sees every company."""
    now = service.now()
    return [
        OrganizationSummaryRead.of(org, access.user_id, now)
        for org in await service.list_visible(access)
    ]


@router.get("/{organization_id}", response_model=OrganizationRead)
async def get_organization(
    organization_id: UUID, access: ReadAccess, service: ServiceDep
) -> OrganizationRead:
    org = await service.get(access, organization_id)
    return OrganizationRead.of(org, access.user_id, service.now())


# --- members ------------------------------------------------------------------


@router.get("/{organization_id}/members", response_model=list[MemberRead])
async def list_members(
    organization_id: UUID, access: ReadAccess, service: ServiceDep, identity: IdentityDep
) -> list[MemberRead]:
    now = service.now()
    members = await service.list_members(access, organization_id, identity)
    return [MemberRead.of(member, account, now) for member, account in members]


@router.post(
    "/{organization_id}/members",
    response_model=MemberRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    organization_id: UUID,
    data: MemberCreate,
    access: UpdateAccess,
    service: ServiceDep,
    identity: IdentityDep,
) -> MemberRead:
    """An existing account by email or phone; unknown login — 422."""
    member, account = await service.add_member(
        access, organization_id, data.login, data.role, identity
    )
    return MemberRead.of(member, account, service.now())


@router.patch("/{organization_id}/members/{account_id}", response_model=MemberRead)
async def change_member_role(
    organization_id: UUID,
    account_id: UUID,
    data: MemberUpdate,
    access: UpdateAccess,
    service: ServiceDep,
) -> MemberRead:
    member = await service.change_role(access, organization_id, account_id, data.role)
    return MemberRead.of(member, None, service.now())


@router.delete("/{organization_id}/members/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    organization_id: UUID, account_id: UUID, access: UpdateAccess, service: ServiceDep
) -> None:
    await service.remove_member(access, organization_id, account_id)


@router.post("/{organization_id}/members/{account_id}/poa", response_model=MemberRead)
async def grant_power_of_attorney(
    organization_id: UUID,
    account_id: UUID,
    data: PowerOfAttorneyCreate,
    access: UpdateAccess,
    service: ServiceDep,
) -> MemberRead:
    """Issued by the head confirmed by the registry; replaces the previous one."""
    power_of_attorney = PowerOfAttorney(
        number=data.number,
        issued_at=data.issued_at,
        valid_until=data.valid_until,
        scope=data.scope_permissions(),
    )
    member = await service.grant_power_of_attorney(
        access, organization_id, account_id, power_of_attorney
    )
    return MemberRead.of(member, None, service.now())


# --- financial reports --------------------------------------------------------


@router.get("/{organization_id}/financial-reports", response_model=list[FinancialReportRead])
async def list_financial_reports(
    organization_id: UUID, access: ReadAccess, service: ServiceDep
) -> list[FinancialReportRead]:
    reports = await service.list_reports(access, organization_id)
    return [FinancialReportRead.of(report) for report in reports]


@router.post(
    "/{organization_id}/financial-reports",
    response_model=FinancialReportRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_financial_report(
    organization_id: UUID,
    data: FinancialReportCreate,
    access: UpdateAccess,
    service: ServiceDep,
    response: Response,
) -> FinancialReportRead:
    """Declared report for a period that is over. The same period again
    revises the report (200), a new one is created (201)."""
    figures = ReportFigures(
        revenue=Money(data.revenue),
        expenses=_money(data.expenses),
        net_profit=_money(data.net_profit),
        total_liabilities=_money(data.total_liabilities),
        monthly_debt_payments=_money(data.monthly_debt_payments),
    )
    report, created = await service.submit_report(
        access, organization_id, FiscalPeriod(data.period_year, data.period_quarter), figures
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return FinancialReportRead.of(report)
