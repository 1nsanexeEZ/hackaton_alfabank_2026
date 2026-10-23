"""Financial reports of a company: the declared ones are typed in by its members."""

from decimal import Decimal
from uuid import UUID, uuid4

from src.core.access.access_context import AccessContext
from src.core.domain import Money
from src.core.domain.clock import Clock
from src.core.uow import UnitOfWork
from src.modules.clients.application.dto.reports import FinancialReportRecordDTO, SubmitReportDTO
from src.modules.clients.application.interfaces.outbox import EventOutbox
from src.modules.clients.application.interfaces.repositories import (
    FinancialReportRepository,
    OrganizationRepository,
)
from src.modules.clients.application.mappers.events import stage
from src.modules.clients.application.use_cases.common import (
    actor_of,
    get_organization,
    get_to_change,
)
from src.modules.clients.domain.enums import ReportSource
from src.modules.clients.domain.financial_report import ReportFigures
from src.modules.clients.domain.value_objects import FiscalPeriod


def _money(value: Decimal | None) -> Money | None:
    return Money(value) if value is not None else None


class ListFinancialReportsUseCase:
    def __init__(
        self, organizations: OrganizationRepository, reports: FinancialReportRepository
    ) -> None:
        self._organizations = organizations
        self._reports = reports

    async def execute(
        self, access: AccessContext, organization_id: UUID
    ) -> list[FinancialReportRecordDTO]:
        org = await get_organization(self._organizations, organization_id, access)
        return [FinancialReportRecordDTO.of(r) for r in await self._reports.list_for(org.id)]


class SubmitFinancialReportUseCase:
    """Declared report for a period that is over. The same period again
    revises the report instead of adding a second one."""

    def __init__(
        self,
        uow: UnitOfWork,
        organizations: OrganizationRepository,
        reports: FinancialReportRepository,
        outbox: EventOutbox,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._organizations = organizations
        self._reports = reports
        self._outbox = outbox
        self._clock = clock

    async def execute(
        self, access: AccessContext, organization_id: UUID, data: SubmitReportDTO
    ) -> tuple[FinancialReportRecordDTO, bool]:
        """The report and whether it is new (False — revised)."""
        figures = ReportFigures(
            revenue=Money(data.revenue),
            expenses=_money(data.expenses),
            net_profit=_money(data.net_profit),
            total_liabilities=_money(data.total_liabilities),
            monthly_debt_payments=_money(data.monthly_debt_payments),
        )
        period = FiscalPeriod(data.period_year, data.period_quarter)
        async with self._uow:
            org = await get_to_change(self._organizations, access, organization_id)
            existing = await self._reports.find(org.id, period, ReportSource.DECLARED)
            report = org.submit_financial_report(
                actor_of(access),
                report_id=uuid4(),
                period=period,
                figures=figures,
                now=self._clock.now(),
                existing=existing,
            )
            if existing is None:
                await self._reports.add(report)
            else:
                await self._reports.save(report)
            await stage(self._outbox, report.pull_events(), correlation_id=uuid4())
            await self._uow.commit()
        return FinancialReportRecordDTO.of(report), existing is None
