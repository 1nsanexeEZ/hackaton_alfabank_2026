"""ProjectorFacade reads only the tables: DTOs per contract, filters, sorts, pages."""

from dataclasses import fields
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from src.core.domain.clock import FrozenClock
from src.modules.projector.domain.metrics import DailyMetrics
from src.modules.projector.domain.read_models import OrganizationDashboard, QueueItem, task_stage
from src.modules.projector.domain.timeline import BANK, CLIENT, TimelineEntry
from src.modules.projector.facade import (
    ApplicationOverviewDTO,
    BackofficeMetricsDTO,
    OrganizationDashboardDTO,
    ProjectorFacade,
    QueueItemDTO,
    TimelineEntryDTO,
)
from src.modules.projector.infrastructure.facade_impl import ProjectorFacadeImpl
from tests.projector.unit.factories import T0, overview, queue_item
from tests.projector.world import OpenFacade, OpenStore

ORG, OTHER = uuid4(), uuid4()


def test_implements_the_contract() -> None:
    methods = [name for name in vars(ProjectorFacade) if not name.startswith("_")]
    for name in methods:
        assert callable(getattr(ProjectorFacadeImpl, name)), name


async def test_list_applications_newest_first_with_pages_and_status(
    store: OpenStore, facade: OpenFacade
) -> None:
    rows = [
        overview(organization_id=ORG, updated_at=T0 + timedelta(hours=i), status=status)
        for i, status in enumerate(["in_review", "offer_ready", "in_review"])
    ]
    async with store() as s:
        for row in [*rows, overview(organization_id=OTHER)]:
            await s.save_overview(row)

    async with facade() as projector:
        page = await projector.list_applications(ORG, limit=2)
        second = await projector.list_applications(ORG, limit=2, offset=2)
        in_review = await projector.list_applications(ORG, status="in_review")
        nothing = await projector.list_applications(uuid4())

    assert page.total == 3 and len(page.items) == 2
    assert [i.application_id for i in page.items] == [
        rows[2].application_id,
        rows[1].application_id,
    ]
    assert [i.application_id for i in second.items] == [rows[0].application_id]
    assert in_review.total == 2 and {i.status for i in in_review.items} == {"in_review"}
    assert nothing.total == 0 and nothing.items == ()
    item = page.items[0]
    assert isinstance(item, ApplicationOverviewDTO)
    assert {f.name for f in fields(item)} == {f.name for f in fields(ApplicationOverviewDTO)}
    assert item.amount == Decimal("3000000") and item.updated_at.tzinfo is not None


async def test_dashboard(store: OpenStore, facade: OpenFacade) -> None:
    async with store() as s:
        await s.save_dashboard(
            OrganizationDashboard(
                ORG,
                active_applications=2,
                action_required_count=1,
                pre_approved_max_amount=Decimal("5000000"),
                pre_approved_rate_from=Decimal("22.5"),
                last_activity_at=T0,
            )
        )
    async with facade() as projector:
        dashboard = await projector.get_organization_dashboard(ORG)
        assert await projector.get_organization_dashboard(OTHER) is None
    assert dashboard == OrganizationDashboardDTO(
        organization_id=ORG,
        active_applications=2,
        action_required_count=1,
        pre_approved_max_amount=Decimal("5000000"),
        pre_approved_rate_from=Decimal("22.5"),
        last_activity_at=T0,
    )


@pytest.fixture
async def queue(store: OpenStore) -> dict[str, QueueItem]:
    items = {
        "soon": queue_item(due_at=T0 + timedelta(hours=1), amount=Decimal("1000000"), score=700),
        "late": queue_item(due_at=T0 + timedelta(days=2), amount=Decimal("9000000"), score=520),
        "no_due": queue_item(
            due_at=None, amount=None, score=None, created_at=T0 - timedelta(hours=1)
        ),
        "taken": queue_item(
            due_at=T0 + timedelta(hours=3),
            amount=Decimal("5000000"),
            score=610,
            status="in_progress",
            assignee_id=uuid4(),
            source_version=task_stage("in_progress"),
        ),
        "done": queue_item(status="done", source_version=task_stage("done")),
        "other_role": queue_item(candidate_role="risk_officer"),
    }
    async with store() as s:
        for item in items.values():
            await s.save_queue_item(item)
    return items


@pytest.mark.parametrize(
    "sort,expected",
    [
        ("due_at", ["soon", "taken", "late", "no_due"]),
        ("amount", ["late", "taken", "soon", "no_due"]),
        ("score", ["late", "taken", "soon", "no_due"]),
        ("created_at", ["no_due", "soon", "late", "taken"]),
    ],
)
async def test_queue_sorts(
    queue: dict[str, QueueItem], facade: OpenFacade, sort: str, expected: list[str]
) -> None:
    async with facade() as projector:
        page = await projector.get_underwriting_queue("underwriter", sort=sort)  # type: ignore[arg-type]
    names = {item.task_id: name for name, item in queue.items()}
    assert page.total == 4
    ordered = [names[i.task_id] for i in page.items]
    if sort == "created_at":
        # same created_at for three of them: the task id decides, only the oldest is fixed
        assert ordered[0] == "no_due" and set(ordered) == set(expected)
    else:
        assert ordered == expected


async def test_queue_status_filter_and_pages(
    queue: dict[str, QueueItem], facade: OpenFacade
) -> None:
    async with facade() as projector:
        first = await projector.get_underwriting_queue("underwriter", limit=3)
        rest = await projector.get_underwriting_queue("underwriter", limit=3, offset=3)
        taken = await projector.get_underwriting_queue("underwriter", status="in_progress")
        done = await projector.get_underwriting_queue("underwriter", status="done")
        closed = await projector.get_underwriting_queue("underwriter", status="closed")
    assert (first.total, len(first.items), len(rest.items)) == (4, 3, 1)
    assert taken.total == 1 and taken.items[0].assignee_id is not None
    assert done.total == closed.total == 1


async def test_queue_overdue_is_computed_with_the_clock(
    queue: dict[str, QueueItem], facade: OpenFacade, clock: FrozenClock
) -> None:
    clock.set(T0 + timedelta(hours=2))
    async with facade() as projector:
        items = (await projector.get_underwriting_queue("underwriter")).items
    overdue = {i.task_id for i in items if i.overdue}
    assert overdue == {queue["soon"].task_id}

    clock.set(T0 + timedelta(days=3))
    async with facade() as projector:
        items = (await projector.get_underwriting_queue("underwriter")).items
    assert sum(i.overdue for i in items) == 3  # everything with a deadline
    assert isinstance(items[0], QueueItemDTO)
    assert {f.name for f in fields(items[0])} == {f.name for f in fields(QueueItemDTO)}


async def test_timeline_for_client_and_bank(store: OpenStore, facade: OpenFacade) -> None:
    app = uuid4()
    entries = [
        TimelineEntry.of_event(uuid4(), app, T0 + timedelta(minutes=i), kind, "t", audience)
        for i, (kind, audience) in enumerate(
            [("status", CLIENT), ("task", BANK), ("decision", CLIENT), ("stage", BANK)]
        )
    ]
    async with store() as s:
        for entry in reversed(entries):
            assert await s.add_timeline_entry(entry)
        assert not await s.add_timeline_entry(entries[0])
        await s.add_timeline_entry(
            TimelineEntry.of_event(uuid4(), uuid4(), T0, "status", "x", CLIENT)
        )

    async with facade() as projector:
        client = await projector.get_timeline(app, "client")
        bank = await projector.get_timeline(app, "bank")
    assert [e.id for e in client] == [entries[0].id, entries[2].id]
    assert [e.id for e in bank] == [e.id for e in entries]
    assert all(isinstance(e, TimelineEntryDTO) and e.at.tzinfo for e in bank)


async def test_backoffice_metrics_for_a_period(store: OpenStore, facade: OpenFacade) -> None:
    day = date(2026, 10, 20)
    async with store() as s:
        await s.save_metrics(
            DailyMetrics(
                day,
                "UNSECURED",
                submitted=2,
                approved=1,
                auto_decisions=1,
                decision_time_total_sec=600,
                decision_time_count=1,
            )
        )
        await s.save_metrics(
            DailyMetrics(
                day + timedelta(days=1),
                "CREDIT_LINE",
                submitted=1,
                counter_offers=1,
                manual_reviews=1,
                decision_time_total_sec=7200,
                decision_time_count=1,
            )
        )
        await s.save_metrics(DailyMetrics(day + timedelta(days=5), "OVERDRAFT", submitted=9))
        # an empty cell is not stored
        await s.save_metrics(DailyMetrics(day, "SECURED"))

    async with facade() as projector:
        metrics = await projector.get_backoffice_metrics(day, day + timedelta(days=1))
        first_day = await projector.get_backoffice_metrics(day, day)
        empty = await projector.get_backoffice_metrics(date(2027, 1, 1), date(2027, 1, 31))

    assert isinstance(metrics, BackofficeMetricsDTO)
    assert (metrics.date_from, metrics.date_to) == (day, day + timedelta(days=1))
    assert [(r.day, r.product_code) for r in metrics.rows] == [
        (day, "UNSECURED"),
        (day + timedelta(days=1), "CREDIT_LINE"),
    ]
    assert metrics.rows[1].avg_time_to_decision_sec == 7200.0
    assert (metrics.submitted, metrics.decided) == (3, 2)
    assert metrics.auto_decision_share == 0.5
    assert metrics.avg_time_to_decision_sec == 3900.0
    assert first_day.auto_decision_share == 1.0
    assert (empty.rows, empty.submitted, empty.auto_decision_share) == ((), 0, None)


async def test_empty_metrics_cell_is_removed(store: OpenStore, facade: OpenFacade) -> None:
    day = date(2026, 10, 20)
    async with store() as s:
        await s.save_metrics(DailyMetrics(day, "UNSECURED", submitted=1))
    async with store() as s:
        await s.save_metrics(DailyMetrics(day, "UNSECURED"))
    async with facade() as projector:
        assert (await projector.get_backoffice_metrics(day, day)).rows == ()
