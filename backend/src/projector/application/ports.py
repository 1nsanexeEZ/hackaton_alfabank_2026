from datetime import date
from typing import Protocol
from uuid import UUID

from src.projector.domain.metrics import DailyMetrics
from src.projector.domain.read_models import (
    ApplicationOverview,
    OrganizationDashboard,
    QueueItem,
)
from src.projector.domain.timeline import TimelineEntry


class FacadeLookup(Protocol):
    """Facades of other modules bound to the current transaction (`ctx.facade`).
    An unregistered facade raises a LookupError (FacadeNotRegisteredError)."""

    def __call__[T](self, key: type[T]) -> T: ...


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
