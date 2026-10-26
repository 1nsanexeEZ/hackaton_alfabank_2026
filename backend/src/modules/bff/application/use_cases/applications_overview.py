"""The admin's overview of the applications in one call: the funnel, where the applications
are now, products and amounts over every application (the projector groups them in the
database), and the latest ones."""

from collections import defaultdict
from decimal import Decimal

from src.modules.bff.application.dto.applications_overview import (
    ApplicationsOverviewDTO,
    CountDTO,
    ProductCountDTO,
)
from src.modules.bff.application.interfaces.neighbours import Neighbours
from src.modules.projector.facade import (
    ApplicationGroupDTO,
    ProjectorFacade,
)

SUBMITTED = frozenset(
    {
        "submitted",
        "in_review",
        "info_requested",
        "offer_ready",
        "signing",
        "signed",
        "disbursed",
        "rejected",
        "offer_declined",
        "expired",
        "cancelled",
    }
)
# How far an application got, not where it is now: a rejected one had a decision, a declined
# or expired offer was approved. A cancelled one was submitted and stopped there.
FUNNEL: tuple[tuple[str, frozenset[str] | None], ...] = (
    ("started", None),
    ("submitted", SUBMITTED),
    (
        "decided",
        frozenset(
            {
                "offer_ready",
                "signing",
                "signed",
                "disbursed",
                "rejected",
                "offer_declined",
                "expired",
            }
        ),
    ),
    (
        "approved",
        frozenset({"offer_ready", "signing", "signed", "disbursed", "offer_declined", "expired"}),
    ),
    ("signed", frozenset({"signed", "disbursed"})),
    ("disbursed", frozenset({"disbursed"})),
)


class ApplicationsOverviewUseCase:
    def __init__(self, neighbours: Neighbours) -> None:
        self._n = neighbours

    async def execute(self, latest: int) -> ApplicationsOverviewDTO:
        stats = await self._n(ProjectorFacade).get_application_stats(latest)
        groups = stats.groups

        def reached(statuses: frozenset[str] | None) -> list[ApplicationGroupDTO]:
            return [g for g in groups if statuses is None or g.status in statuses]

        funnel = tuple(
            CountDTO(stage, sum(g.count for g in reached(statuses)), _amount(reached(statuses)))
            for stage, statuses in FUNNEL
        )
        by_status: dict[str, list[ApplicationGroupDTO]] = defaultdict(list)
        by_product: dict[str, list[ApplicationGroupDTO]] = defaultdict(list)
        for group in groups:
            by_status[group.status].append(group)
            by_product[group.product_code].append(group)
        products = sorted(
            (
                ProductCountDTO(
                    code, items[0].product_name, sum(g.count for g in items), _amount(items)
                )
                for code, items in by_product.items()
            ),
            key=lambda p: (-p.count, p.product_code),
        )
        submitted = reached(SUBMITTED)
        return ApplicationsOverviewDTO(
            total=funnel[0].count,
            submitted=sum(g.count for g in submitted),
            requested_amount=_amount(submitted),
            approved=funnel[3].count,
            decided=funnel[2].count,
            funnel=funnel,
            statuses=tuple(
                CountDTO(status, sum(g.count for g in items), _amount(items))
                for status, items in sorted(by_status.items())
            ),
            products=tuple(products),
            amount_buckets=stats.amount_buckets,
            latest=stats.latest,
        )


def _amount(groups: list[ApplicationGroupDTO]) -> Decimal:
    return sum((g.amount for g in groups), Decimal(0))
