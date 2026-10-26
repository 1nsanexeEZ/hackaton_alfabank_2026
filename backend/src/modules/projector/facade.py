"""Projector contract: denormalized read models for lists, queues and
dashboards. No access checks inside — bff checks rights before calling.

The only entry point for other modules: the protocol below and the DTO it returns
(defined in `application/dto`, re-exported here)."""

from datetime import date
from typing import Protocol
from uuid import UUID

from src.modules.projector.application.dto.applications import (
    ApplicationOverviewDTO,
    ApplicationPageDTO,
    OrganizationDashboardDTO,
)
from src.modules.projector.application.dto.metrics import BackofficeMetricsDTO, DailyMetricsDTO
from src.modules.projector.application.dto.queue import QueueItemDTO, QueuePageDTO
from src.modules.projector.application.dto.timeline import TimelineEntryDTO
from src.modules.projector.domain.enums import ActionRequired, Audience, QueueSort, ReviewKind

__all__ = [
    "ActionRequired",
    "ApplicationOverviewDTO",
    "ApplicationPageDTO",
    "Audience",
    "BackofficeMetricsDTO",
    "DailyMetricsDTO",
    "OrganizationDashboardDTO",
    "ProjectorFacade",
    "QueueItemDTO",
    "QueuePageDTO",
    "QueueSort",
    "ReviewKind",
    "TimelineEntryDTO",
]


class ProjectorFacade(Protocol):
    async def list_applications(
        self,
        organization_id: UUID,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> ApplicationPageDTO: ...

    async def get_organization_dashboard(
        self, organization_id: UUID
    ) -> OrganizationDashboardDTO | None: ...

    async def get_underwriting_queue(
        self,
        role: str,
        status: str = "open",
        sort: QueueSort = "due_at",
        limit: int = 20,
        offset: int = 0,
        review: ReviewKind | None = None,
    ) -> QueuePageDTO: ...

    async def get_timeline(
        self, application_id: UUID, audience: Audience
    ) -> list[TimelineEntryDTO]:
        """audience=client returns client entries only; bank gets everything."""
        ...

    async def get_backoffice_metrics(
        self, date_from: date, date_to: date
    ) -> BackofficeMetricsDTO: ...
