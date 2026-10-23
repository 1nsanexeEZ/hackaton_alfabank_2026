"""Snapshot of a company for the application and the decision: requisites,
registry data, the check and the two latest annual reports."""

from uuid import UUID

from src.core.domain.clock import Clock
from src.modules.clients.application.dto.organizations import discrepancy_dto
from src.modules.clients.application.dto.reports import amount
from src.modules.clients.application.dto.snapshot import (
    FinancialReportDTO,
    OrganizationSnapshotDTO,
)
from src.modules.clients.application.interfaces.repositories import (
    FinancialReportRepository,
    OrganizationRepository,
)
from src.modules.clients.application.use_cases.common import get_organization
from src.modules.clients.domain.enums import ReportSource
from src.modules.clients.domain.financial_report import FinancialReport

SNAPSHOT_REPORTS = 2
# One annual report per year goes to the snapshot: what the company declared
# first, then what the bank got from other sources.
SOURCE_PRIORITY = (ReportSource.DECLARED, ReportSource.FNS, ReportSource.BANK_STATEMENT)


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


class GetSnapshotUseCase:
    def __init__(
        self,
        organizations: OrganizationRepository,
        reports: FinancialReportRepository,
        clock: Clock,
    ) -> None:
        self._organizations = organizations
        self._reports = reports
        self._clock = clock

    async def execute(self, organization_id: UUID) -> OrganizationSnapshotDTO:
        """NotFoundError for an unknown company."""
        org = await get_organization(self._organizations, organization_id)
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
            discrepancies=tuple(discrepancy_dto(d) for d in org.verification.discrepancies),
            head_name=org.registry_head.full if org.registry_head else None,
            financial_reports=tuple(_report_dto(r) for r in reports),
            snapshot_at=now,
        )
