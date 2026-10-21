"""ClientsFacade for other modules; also the MemberOrganizationsResolver port
of the `org_member` policy. Built per session: reads join the caller's
transaction. Rights are computed at the clock's `now`."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.domain.financial_report import FinancialReport, ReportSource
from src.clients.domain.organization import Organization, organization_not_found
from src.clients.domain.rights import OrgPermission
from src.clients.facade import (
    DiscrepancyDTO,
    FinancialReportDTO,
    OrganizationSnapshotDTO,
    OrganizationSummaryDTO,
)
from src.clients.infrastructure.repositories import (
    SqlAlchemyFinancialReportRepository,
    SqlAlchemyOrganizationRepository,
)
from src.core.domain import Money
from src.core.domain.clock import Clock

SNAPSHOT_REPORTS = 2
# One annual report per year goes to the snapshot: what the company declared
# first, then what the bank got from other sources.
SOURCE_PRIORITY = (ReportSource.DECLARED, ReportSource.FNS, ReportSource.BANK_STATEMENT)


def _permission(value: str) -> OrgPermission:
    try:
        return OrgPermission(str(value))
    except ValueError:
        raise ValueError(f"Unknown organization permission {value!r}") from None


def _names(permissions: frozenset[OrgPermission]) -> frozenset[str]:
    return frozenset(p.value for p in permissions)


def latest_annual(
    reports: list[FinancialReport], limit: int = SNAPSHOT_REPORTS
) -> list[FinancialReport]:
    by_year: dict[int, FinancialReport] = {}
    for report in reports:
        if not report.period.is_annual:
            continue
        current = by_year.get(report.period.year)
        if current is None or SOURCE_PRIORITY.index(report.source) < SOURCE_PRIORITY.index(
            current.source
        ):
            by_year[report.period.year] = report
    return [by_year[year] for year in sorted(by_year, reverse=True)[:limit]]


def amount(value: Money | None) -> Decimal | None:
    return value.amount if value is not None else None


def _report_dto(report: FinancialReport) -> FinancialReportDTO:
    figures = report.figures
    return FinancialReportDTO(
        period_year=report.period.year,
        period_quarter=report.period.quarter,
        source=report.source.value,  # type: ignore[arg-type]
        revenue=figures.revenue.amount,
        expenses=amount(figures.expenses),
        net_profit=amount(figures.net_profit),
        total_liabilities=amount(figures.total_liabilities),
        monthly_debt_payments=amount(figures.monthly_debt_payments),
    )


class ClientsFacadeImpl:
    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self._organizations = SqlAlchemyOrganizationRepository(session)
        self._reports = SqlAlchemyFinancialReportRepository(session)
        self._clock = clock

    async def ensure_can(self, account_id: UUID, organization_id: UUID, permission: str) -> None:
        org = await self._get(organization_id)
        org.ensure_can(account_id, _permission(permission), self._clock.now())

    async def get_member_permissions(
        self, account_id: UUID, organization_id: UUID
    ) -> frozenset[str]:
        org = await self._organizations.get(organization_id)
        if org is None:
            return frozenset()
        return _names(org.permissions_of(account_id, self._clock.now()))

    async def get_member_organization_ids(self, account_id: UUID) -> frozenset[UUID]:
        return await self._organizations.member_organization_ids(account_id)

    async def member_organization_ids(self, account_id: UUID) -> frozenset[UUID]:
        """MemberOrganizationsResolver: companies where the account is a member."""
        return await self.get_member_organization_ids(account_id)

    async def get_snapshot(self, organization_id: UUID) -> OrganizationSnapshotDTO:
        org = await self._get(organization_id)
        now = self._clock.now()
        requisites = org.requisites
        reports = latest_annual(await self._reports.list_for(org.id))
        return OrganizationSnapshotDTO(
            id=org.id,
            inn=requisites.inn.value,
            ogrn=requisites.ogrn.value,
            kpp=requisites.kpp.value if requisites.kpp else None,
            legal_form=requisites.legal_form.value,  # type: ignore[arg-type]
            name=org.name,
            registered_at=org.registered_at,
            business_age_months=org.business_age_months(now),
            okved_main=org.okved_main.value,
            okved_extra=tuple(code.value for code in org.okved_extra),
            region_code=org.address.region_code,
            tax_regime=org.tax_regime.value,
            employees_count=org.employees_count,
            registry_status=org.registry_status.value,  # type: ignore[arg-type]
            verification_status=org.verification.status.value,  # type: ignore[arg-type]
            discrepancies=tuple(
                DiscrepancyDTO(field=d.field, declared=d.declared, registry=d.registry)
                for d in org.verification.discrepancies
            ),
            head_name=org.registry_head.full if org.registry_head else None,
            financial_reports=tuple(_report_dto(r) for r in reports),
            snapshot_at=now,
        )

    async def list_my_organizations(self, account_id: UUID) -> list[OrganizationSummaryDTO]:
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

    async def list_members(
        self, organization_id: UUID, permission: str | None = None
    ) -> list[UUID]:
        org = await self._organizations.get(organization_id)
        if org is None:
            return []
        wanted = _permission(permission) if permission is not None else None
        return org.members_with(wanted, self._clock.now())

    async def _get(self, organization_id: UUID) -> Organization:
        org = await self._organizations.get(organization_id)
        if org is None:
            raise organization_not_found()
        return org
