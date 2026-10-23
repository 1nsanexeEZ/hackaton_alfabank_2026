"""What the use cases need from storage; implemented in infrastructure/repositories."""

from typing import Protocol
from uuid import UUID

from src.core.access.access_context import AccessContext
from src.modules.clients.domain.business_plan import BusinessPlan
from src.modules.clients.domain.enums import ReportSource
from src.modules.clients.domain.financial_report import FinancialReport
from src.modules.clients.domain.organization import Organization
from src.modules.clients.domain.value_objects import FiscalPeriod


class OrganizationRepository(Protocol):
    async def get(
        self, organization_id: UUID, access: AccessContext | None = None
    ) -> Organization | None:
        """With `access` — None also for a company hidden by the caller's policies."""
        ...

    async def list_visible(self, access: AccessContext) -> list[Organization]: ...

    async def list_for_member(self, account_id: UUID) -> list[Organization]: ...

    async def get_by_inn(self, inn: str) -> Organization | None: ...

    async def member_organization_ids(self, account_id: UUID) -> frozenset[UUID]: ...

    async def add(self, org: Organization) -> None: ...

    async def save(self, org: Organization) -> None:
        """ConflictError if the company was changed concurrently."""
        ...


class FinancialReportRepository(Protocol):
    async def list_for(self, organization_id: UUID) -> list[FinancialReport]: ...

    async def find(
        self, organization_id: UUID, period: FiscalPeriod, source: ReportSource
    ) -> FinancialReport | None: ...

    async def add(self, report: FinancialReport) -> None: ...

    async def save(self, report: FinancialReport) -> None: ...


class BusinessPlanRepository(Protocol):
    """One plan per company."""

    async def get(self, organization_id: UUID) -> BusinessPlan | None: ...

    async def add(self, plan: BusinessPlan) -> None: ...

    async def save(self, plan: BusinessPlan) -> None:
        """ConflictError if the plan was revised concurrently."""
        ...
