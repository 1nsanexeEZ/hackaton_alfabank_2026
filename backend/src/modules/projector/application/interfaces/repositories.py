from datetime import date
from typing import Protocol
from uuid import UUID

from src.modules.projector.domain.enums import QueueSort
from src.modules.projector.domain.metrics import DailyMetrics
from src.modules.projector.domain.read_models import (
    ApplicationOverview,
    OrganizationDashboard,
    QueueItem,
)
from src.modules.projector.domain.timeline import TimelineEntry


class ReadModelStore(Protocol):
    """Storage of every read model. Records are returned as copies: a change
    is stored only by the matching save_*()."""

    async def get_overview(self, application_id: UUID) -> ApplicationOverview | None: ...

    async def save_overview(self, overview: ApplicationOverview) -> None: ...

    async def overviews_for_metrics(
        self, day: date, product_code: str
    ) -> list[ApplicationOverview]:
        """Rows of the product submitted, decided or routed to manual review that day."""
        ...

    async def count_applications(
        self, organization_id: UUID, active_statuses: frozenset[str]
    ) -> tuple[int, int]:
        """(active applications, applications waiting for the client)."""
        ...

    async def get_queue_item(self, task_id: UUID) -> QueueItem | None: ...

    async def queue_items_of(self, application_id: UUID) -> list[QueueItem]: ...

    async def save_queue_item(self, item: QueueItem) -> None: ...

    async def add_timeline_entry(self, entry: TimelineEntry) -> bool:
        """False when the entry of that event is already there."""
        ...

    async def get_dashboard(self, organization_id: UUID) -> OrganizationDashboard | None: ...

    async def save_dashboard(self, dashboard: OrganizationDashboard) -> None: ...

    async def save_metrics(self, metrics: DailyMetrics) -> None:
        """An empty cell is removed."""
        ...

    async def clear(self) -> None:
        """Remove every read model row (rebuild)."""
        ...


class ReadModelQueries(Protocol):
    """Reads behind the facade: filters, sorts and pages over the read models."""

    async def overviews_of(
        self, organization_id: UUID, status: str | None, limit: int, offset: int
    ) -> tuple[list[ApplicationOverview], int]:
        """A page of the organization's rows, recently updated first, and the total."""
        ...

    async def get_dashboard(self, organization_id: UUID) -> OrganizationDashboard | None: ...

    async def queue_of(
        self, role: str, statuses: tuple[str, ...], sort: QueueSort, limit: int, offset: int
    ) -> tuple[list[QueueItem], int]:
        """A page of the role's tasks in those statuses, in the `sort` order, and the total."""
        ...

    async def timeline_of(self, application_id: UUID, client_only: bool) -> list[TimelineEntry]:
        """Entries by time; client_only leaves the client entries alone."""
        ...

    async def metrics_between(self, date_from: date, date_to: date) -> list[DailyMetrics]:
        """Cells of the days from date_from to date_to inclusive, by day and product."""
        ...
