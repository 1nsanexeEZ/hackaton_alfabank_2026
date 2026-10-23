"""Financial reports: one row per company, period and source."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions.exceptions import ConflictError
from src.modules.clients.application.interfaces.repositories import FinancialReportRepository
from src.modules.clients.domain.enums import ReportSource
from src.modules.clients.domain.financial_report import FinancialReport
from src.modules.clients.domain.value_objects import FiscalPeriod
from src.modules.clients.infrastructure.database.models import FinancialReportModel
from src.modules.clients.infrastructure.repositories.mappers import (
    ANNUAL,
    figures_values,
    report_to_entity,
)


class SqlAlchemyFinancialReportRepository(FinancialReportRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for(self, organization_id: UUID) -> list[FinancialReport]:
        """Newest year first; within a year — the annual report, then quarters 4..1."""
        stmt = select(FinancialReportModel).where(
            FinancialReportModel.organization_id == organization_id
        )
        models = (await self._session.scalars(stmt)).all()
        ordered = sorted(
            models,
            key=lambda m: (-m.period_year, m.period_quarter != ANNUAL, -m.period_quarter, m.source),
        )
        return [report_to_entity(m) for m in ordered]

    async def find(
        self, organization_id: UUID, period: FiscalPeriod, source: ReportSource
    ) -> FinancialReport | None:
        model = await self._find_model(organization_id, period, source)
        return report_to_entity(model) if model is not None else None

    async def add(self, report: FinancialReport) -> None:
        self._session.add(
            FinancialReportModel(
                id=report.id,
                organization_id=report.organization_id,
                period_year=report.period.year,
                period_quarter=report.period.quarter or ANNUAL,
                source=report.source.value,
                **figures_values(report),
            )
        )
        try:
            await self._session.flush()
        except IntegrityError:
            # Someone stored a report for the same period meanwhile.
            raise ConflictError(
                "A report for this period is being submitted already, retry",
                details={"code": "report_exists"},
            ) from None

    async def save(self, report: FinancialReport) -> None:
        model = await self._session.get(FinancialReportModel, report.id)
        if model is None:
            raise LookupError(f"Financial report {report.id} is not stored")
        for name, value in figures_values(report).items():
            setattr(model, name, value)
        await self._session.flush()

    async def _find_model(
        self, organization_id: UUID, period: FiscalPeriod, source: ReportSource
    ) -> FinancialReportModel | None:
        stmt = select(FinancialReportModel).where(
            FinancialReportModel.organization_id == organization_id,
            FinancialReportModel.period_year == period.year,
            FinancialReportModel.period_quarter == (period.quarter or ANNUAL),
            FinancialReportModel.source == source.value,
        )
        return (await self._session.scalars(stmt)).one_or_none()
