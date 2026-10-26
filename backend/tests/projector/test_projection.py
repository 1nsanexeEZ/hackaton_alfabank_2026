"""Every event through the live path (core MessageProcessor + projector
subscriptions) into the read model tables, read back through the facade."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.domain.clock import FrozenClock
from src.core.facades import FacadeRegistry
from src.core.messaging.contracts.applications import (
    ApplicationCancelled,
    ApplicationStatusChanged,
    ApplicationSubmitted,
    OfferTerms,
)
from src.core.messaging.contracts.clients import FinancialReportSubmitted, MemberAdded
from src.core.messaging.contracts.decision import DecisionMade, PreApprovedOffersUpdated
from src.core.messaging.contracts.process import (
    ProcessCompleted,
    ProcessStarted,
    StepCompleted,
    UserTaskCompleted,
    UserTaskCreated,
)
from src.core.messaging.envelope import Envelope
from src.core.messaging.outbox import build_envelope
from src.modules.applications.facade import ApplicationsFacade
from src.modules.projector.presentation.rebuild import apply_one
from tests.projector.world import (
    Consumer,
    OpenFacade,
    World,
    decision,
    dump_tables,
    offer,
    pre_approved,
    scoring_result,
    task,
)

T0 = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
DAY = date(2026, 10, 20)
ORG = UUID("00000000-0000-4000-8000-00000000000a")


def submitted(application_id: UUID, amount: str = "3000000") -> ApplicationSubmitted:
    return ApplicationSubmitted(
        application_id=application_id,
        organization_id=ORG,
        product_code="UNSECURED",
        amount=Decimal(amount),
        term_months=24,
        purpose="working_capital",
    )


def changed(
    application_id: UUID, source: str, target: str, **extra: Any
) -> ApplicationStatusChanged:
    return ApplicationStatusChanged(
        application_id=application_id,
        organization_id=ORG,
        from_status=source,
        to_status=target,
        **extra,
    )


def decided(application_id: UUID, outcome: str, by: str = "auto", **extra: Any) -> DecisionMade:
    return DecisionMade(
        application_id=application_id,
        decision_id=uuid4(),
        outcome=outcome,  # type: ignore[arg-type]
        decided_by=by,  # type: ignore[arg-type]
        client_explanation="Пояснение для клиента",
        **extra,
    )


def task_created(task_id: UUID, application_id: UUID, due_at: datetime | None) -> UserTaskCreated:
    return UserTaskCreated(
        task_id=task_id,
        process_id=uuid4(),
        application_id=application_id,
        task_type="manual_review",
        candidate_role="underwriter",
        due_at=due_at,
    )


def task_completed(task_id: UUID, application_id: UUID) -> UserTaskCompleted:
    return UserTaskCompleted(
        task_id=task_id, application_id=application_id, completed_by=uuid4(), result={}
    )


# --- applications.events -------------------------------------------------------


async def test_submission_creates_overview_dashboard_and_metrics(
    world: World, consumer: Consumer, facade: OpenFacade
) -> None:
    app = uuid4()
    world.card(app, ORG, number="КР-2026-000007", updated_at=T0, submitted_at=T0)

    assert await consumer.deliver(submitted(app), T0) == "processed"

    async with facade() as projector:
        page = await projector.list_applications(ORG)
        dashboard = await projector.get_organization_dashboard(ORG)
        metrics = await projector.get_backoffice_metrics(DAY, DAY)
        timeline = await projector.get_timeline(app, "bank")
    assert page.total == 1
    row = page.items[0]
    assert (row.application_id, row.organization_id, row.number) == (app, ORG, "КР-2026-000007")
    assert (row.product_code, row.product_name) == ("UNSECURED", "Кредит без залога")
    assert (row.amount, row.term_months, row.status) == (Decimal("3000000"), 24, "submitted")
    assert (row.action_required, row.offer_amount, row.offer_rate) == ("none", None, None)
    assert row.submitted_at == T0 and row.updated_at == T0
    assert dashboard is not None
    assert (dashboard.active_applications, dashboard.action_required_count) == (1, 0)
    assert dashboard.last_activity_at == T0 and dashboard.pre_approved_max_amount is None
    assert [(r.day, r.product_code, r.submitted) for r in metrics.rows] == [(DAY, "UNSECURED", 1)]
    assert timeline == []  # the status change carries the entry


async def test_status_change_updates_overview_and_client_timeline(
    world: World, consumer: Consumer, facade: OpenFacade
) -> None:
    app, at = uuid4(), T0 + timedelta(minutes=11)
    world.card(
        app,
        ORG,
        status="offer_ready",
        version=4,
        updated_at=at,
        submitted_at=T0,
        offer=offer("2500000", "24.5", uuid4(), T0 + timedelta(days=30)),
    )

    await consumer.deliver(changed(app, "in_review", "offer_ready"), at)

    async with facade() as projector:
        row = (await projector.list_applications(ORG)).items[0]
        dashboard = await projector.get_organization_dashboard(ORG)
        client = await projector.get_timeline(app, "client")
    assert (row.status, row.action_required) == ("offer_ready", "offer")
    assert (row.offer_amount, row.offer_rate) == (Decimal("2500000"), Decimal("24.5"))
    assert dashboard is not None and dashboard.action_required_count == 1
    assert len(client) == 1
    entry = client[0]
    assert (entry.kind, entry.audience, entry.title) == (
        "status",
        "client",
        "Готово предложение банка",
    )
    assert (entry.application_id, entry.at) == (app, at)
    assert entry.details == {
        "from_status": "in_review",
        "to_status": "offer_ready",
        "client_stage": None,
    }


async def test_closed_application_is_no_longer_active(
    world: World, consumer: Consumer, facade: OpenFacade
) -> None:
    app = uuid4()
    world.card(app, ORG, updated_at=T0, submitted_at=T0)
    await consumer.deliver(submitted(app), T0)
    world.update_card(app, status="cancelled", version=3, updated_at=T0 + timedelta(hours=1))
    await consumer.deliver(
        ApplicationCancelled(application_id=app, organization_id=ORG), T0 + timedelta(hours=1)
    )

    async with facade() as projector:
        dashboard = await projector.get_organization_dashboard(ORG)
        cancelled = await projector.list_applications(ORG, status="cancelled")
    assert dashboard is not None and dashboard.active_applications == 0
    assert cancelled.total == 1


# --- process.events ------------------------------------------------------------


async def test_process_steps_client_sees_stages_bank_sees_everything(
    world: World, consumer: Consumer, facade: OpenFacade
) -> None:
    app, process = uuid4(), uuid4()
    world.card(app, ORG, status="in_review", version=3, updated_at=T0, submitted_at=T0)
    await consumer.deliver(
        ProcessStarted(process_id=process, application_id=app, workflow_code="express_v1"), T0
    )
    await consumer.deliver(
        StepCompleted(
            process_id=process,
            application_id=app,
            node_id="fetch",
            step_code="fetch_enrichment",
            client_stage="Проверяем данные о компании",
        ),
        T0 + timedelta(minutes=1),
    )
    await consumer.deliver(
        StepCompleted(process_id=process, application_id=app, node_id="s", step_code="score"),
        T0 + timedelta(minutes=2),
    )
    await consumer.deliver(
        ProcessCompleted(process_id=process, application_id=app, outcome="APPROVE"),
        T0 + timedelta(minutes=3),
    )

    async with facade() as projector:
        client = await projector.get_timeline(app, "client")
        bank = await projector.get_timeline(app, "bank")
    assert [e.title for e in client] == ["Проверяем данные о компании"]
    assert [e.kind for e in bank] == ["stage"] * 4
    assert [e.audience for e in bank] == ["bank", "client", "bank", "bank"]
    assert [e.at for e in bank] == sorted(e.at for e in bank)


async def test_task_goes_to_the_queue_and_leaves_open_when_closed(
    world: World, consumer: Consumer, facade: OpenFacade, clock: FrozenClock
) -> None:
    app, task_id = uuid4(), uuid4()
    created, due = T0 + timedelta(minutes=11), T0 + timedelta(days=1, minutes=11)
    clock.set(T0 + timedelta(hours=1))
    world.card(
        app,
        ORG,
        number="КР-2026-000102",
        product_code="CREDIT_LINE",
        amount=Decimal("12000000"),
        status="in_review",
        version=3,
        updated_at=T0,
        submitted_at=T0,
    )
    world.scoring.add_result(scoring_result(app, 610, "C", ("cash_gap_forecast",)))
    world.decision.add_decision(
        decision(app, "MANUAL_REVIEW", decided_at=T0, reason_codes=("AMOUNT_ABOVE_AUTO_LIMIT",))
    )
    world.process.add_task(task(task_id, app, created_at=created, due_at=due))

    await consumer.deliver(task_created(task_id, app, due), created)

    async with facade() as projector:
        queue = await projector.get_underwriting_queue("underwriter")
        other_role = await projector.get_underwriting_queue("risk_officer")
    assert queue.total == 1 and other_role.total == 0
    item = queue.items[0]
    assert (item.task_id, item.application_id, item.number) == (task_id, app, "КР-2026-000102")
    assert (item.company_name, item.inn) == (
        world.applications.cards[app].org_snapshot.name,  # type: ignore[union-attr]
        world.applications.cards[app].org_snapshot.inn,  # type: ignore[union-attr]
    )
    assert (item.product_code, item.amount) == ("CREDIT_LINE", Decimal("12000000"))
    assert (item.score, item.risk_grade, item.cash_gap) == (610, "C", True)
    assert item.routing_reasons == ("AMOUNT_ABOVE_AUTO_LIMIT",)
    assert item.review == "check"
    assert (item.due_at, item.created_at, item.status) == (due, created, "open")
    assert item.overdue is False and item.assignee_id is None

    underwriter = uuid4()
    world.process.add_task(
        task(task_id, app, created_at=created, due_at=due, status="done", assignee_id=underwriter)
    )
    world.decision.add_decision(
        decision(app, "COUNTER_OFFER", decided_at=T0 + timedelta(hours=3), decided_by="underwriter")
    )
    await consumer.deliver(task_completed(task_id, app), T0 + timedelta(hours=3))

    async with facade() as projector:
        still_open = await projector.get_underwriting_queue("underwriter")
        closed = await projector.get_underwriting_queue("underwriter", status="closed")
        timeline = await projector.get_timeline(app, "bank")
    assert still_open.total == 0 and still_open.items == ()
    assert closed.total == 1
    done = closed.items[0]
    assert (done.status, done.assignee_id, done.overdue) == ("done", underwriter, False)
    # routing reasons belong to the manual review, the final decision has none
    assert done.routing_reasons == ()
    assert [e.kind for e in timeline] == ["task", "task"]
    assert all(e.audience == "bank" for e in timeline)


async def test_task_unknown_to_process_is_built_from_events(
    world: World, consumer: Consumer, facade: OpenFacade
) -> None:
    app, task_id, due = uuid4(), uuid4(), T0 + timedelta(hours=4)
    world.card(app, ORG, status="in_review", version=3, updated_at=T0, submitted_at=T0)

    await consumer.deliver(task_created(task_id, app, due), T0)
    async with facade() as projector:
        item = (await projector.get_underwriting_queue("underwriter")).items[0]
    assert (item.status, item.due_at, item.created_at) == ("open", due, T0)

    await consumer.deliver(task_completed(task_id, app), T0 + timedelta(hours=1))
    async with facade() as projector:
        assert (await projector.get_underwriting_queue("underwriter")).total == 0
        done = await projector.get_underwriting_queue("underwriter", status="done")
    assert done.items[0].status == "done"


async def test_closed_task_is_not_reopened_by_a_stale_read(
    world: World, consumer: Consumer, facade: OpenFacade
) -> None:
    app, task_id = uuid4(), uuid4()
    world.card(app, ORG, status="in_review", version=3, updated_at=T0, submitted_at=T0)
    world.process.add_task(task(task_id, app, created_at=T0, status="done"))
    await consumer.deliver(task_created(task_id, app, None), T0)
    # process answers with an older copy of the task
    world.process.add_task(task(task_id, app, created_at=T0, status="open"))
    await consumer.deliver(
        StepCompleted(process_id=uuid4(), application_id=app, node_id="n", step_code="s"),
        T0 + timedelta(minutes=1),
    )

    async with facade() as projector:
        assert (await projector.get_underwriting_queue("underwriter")).total == 0
        assert (await projector.get_underwriting_queue("underwriter", status="done")).total == 1


# --- decision.events -----------------------------------------------------------


async def test_decision_feeds_metrics_and_timeline(
    world: World, consumer: Consumer, facade: OpenFacade
) -> None:
    app = uuid4()
    world.card(app, ORG, status="in_review", version=3, updated_at=T0, submitted_at=T0)
    await consumer.deliver(submitted(app), T0)
    await consumer.deliver(
        decided(
            app,
            "APPROVE",
            offer=OfferTerms(
                kind="as_requested",
                amount=Decimal("3000000"),
                term_months=24,
                rate=Decimal("23.5"),
                monthly_payment=Decimal("158000"),
                expires_at=T0 + timedelta(days=30),
            ),
        ),
        T0 + timedelta(minutes=10),
    )

    async with facade() as projector:
        metrics = await projector.get_backoffice_metrics(DAY, DAY)
        client = await projector.get_timeline(app, "client")
    cell = metrics.rows[0]
    assert (cell.submitted, cell.approved, cell.auto_decisions, cell.manual_reviews) == (1, 1, 1, 0)
    assert cell.avg_time_to_decision_sec == 600.0
    assert (metrics.submitted, metrics.decided) == (1, 1)
    assert metrics.auto_decision_share == 1.0 and metrics.avg_time_to_decision_sec == 600.0
    assert [(e.kind, e.title) for e in client] == [("decision", "Кредит одобрен")]
    assert client[0].details["offer"]["rate"] == "23.5"


async def test_manual_route_and_underwriter_decision_metrics(
    world: World, consumer: Consumer, facade: OpenFacade
) -> None:
    app = uuid4()
    world.card(app, ORG, status="in_review", version=3, updated_at=T0, submitted_at=T0)
    await consumer.deliver(submitted(app), T0)
    await consumer.deliver(decided(app, "MANUAL_REVIEW"), T0 + timedelta(minutes=5))
    await consumer.deliver(decided(app, "REJECT", "underwriter"), T0 + timedelta(days=1, minutes=5))

    async with facade() as projector:
        metrics = await projector.get_backoffice_metrics(DAY, DAY + timedelta(days=1))
    first, second = metrics.rows
    assert (first.day, first.submitted, first.manual_reviews, first.rejected) == (DAY, 1, 1, 0)
    assert (second.day, second.rejected, second.auto_decisions) == (DAY + timedelta(days=1), 1, 0)
    assert second.avg_time_to_decision_sec == 86700.0
    assert metrics.auto_decision_share == 0.0


async def test_pre_approved_offers_reach_the_dashboard(
    world: World, consumer: Consumer, facade: OpenFacade
) -> None:
    world.decision.set_pre_approved(
        ORG,
        [pre_approved("OVERDRAFT", "5000000", "24.0"), pre_approved("UNSECURED", "3000000", "22")],
    )
    await consumer.deliver(PreApprovedOffersUpdated(organization_id=ORG), T0)

    async with facade() as projector:
        dashboard = await projector.get_organization_dashboard(ORG)
    assert dashboard is not None
    assert dashboard.pre_approved_max_amount == Decimal("5000000")
    assert dashboard.pre_approved_rate_from == Decimal("22")
    assert (dashboard.active_applications, dashboard.last_activity_at) == (0, T0)


# --- clients.events ------------------------------------------------------------


async def test_clients_events_mark_activity_of_the_company(
    consumer: Consumer, facade: OpenFacade
) -> None:
    await consumer.deliver(MemberAdded(organization_id=ORG, account_id=uuid4(), role="owner"), T0)
    later = T0 + timedelta(hours=2)
    await consumer.deliver(FinancialReportSubmitted(organization_id=ORG, period_year=2025), later)

    async with facade() as projector:
        dashboard = await projector.get_organization_dashboard(ORG)
        assert await projector.get_organization_dashboard(uuid4()) is None
    assert dashboard is not None and dashboard.last_activity_at == later


# --- repeats, versions, order ----------------------------------------------------


async def test_repeated_delivery_is_ignored(
    world: World, consumer: Consumer, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    app, event_id = uuid4(), uuid4()
    world.card(app, ORG, status="in_review", version=3, updated_at=T0, submitted_at=T0)
    message = changed(app, "submitted", "in_review")

    assert await consumer.deliver(message, T0, event_id) == "processed"
    before = await dump_tables(session_factory)
    assert await consumer.deliver(message, T0, event_id) == "duplicate"
    assert await dump_tables(session_factory) == before


async def test_the_same_event_twice_without_inbox_changes_nothing(
    world: World, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The rebuild has no inbox: natural keys and recomputation keep it exact."""
    app = uuid4()
    world.card(app, ORG, status="in_review", version=3, updated_at=T0, submitted_at=T0)
    events = [
        (submitted(app), T0),
        (changed(app, "submitted", "in_review"), T0 + timedelta(minutes=1)),
        (decided(app, "APPROVE"), T0 + timedelta(minutes=10)),
    ]
    envelopes = [_envelope(m, at) for m, at in events]
    for envelope, (message, _) in zip(envelopes, events, strict=True):
        await apply_one(session_factory, world.registry, envelope, message)
    once = await dump_tables(session_factory)
    for envelope, (message, _) in zip(envelopes, events, strict=True):
        await apply_one(session_factory, world.registry, envelope, message)

    assert await dump_tables(session_factory) == once
    assert len(once["projector_application_timeline"]) == 2
    assert once["projector_backoffice_metrics"][0]["approved"] == 1


async def test_older_card_does_not_overwrite_a_newer_one(
    world: World, consumer: Consumer, facade: OpenFacade
) -> None:
    app = uuid4()
    world.card(app, ORG, status="offer_ready", version=5, updated_at=T0, submitted_at=T0)
    await consumer.deliver(changed(app, "in_review", "offer_ready"), T0)
    # a late event, and applications answers from a lagging copy
    world.update_card(app, status="in_review", version=3, updated_at=T0 - timedelta(minutes=5))
    await consumer.deliver(
        StepCompleted(process_id=uuid4(), application_id=app, node_id="n", step_code="s"),
        T0 + timedelta(minutes=1),
    )

    async with facade() as projector:
        row = (await projector.list_applications(ORG)).items[0]
    assert (row.status, row.action_required, row.updated_at) == ("offer_ready", "offer", T0)


async def test_decision_before_submission_gives_the_same_metrics(
    world: World, consumer: Consumer, facade: OpenFacade
) -> None:
    app = uuid4()
    world.card(app, ORG, status="in_review", version=3, updated_at=T0, submitted_at=T0)
    await consumer.deliver(decided(app, "REJECT"), T0 + timedelta(minutes=20))
    await consumer.deliver(submitted(app), T0)

    async with facade() as projector:
        cell = (await projector.get_backoffice_metrics(DAY, DAY)).rows[0]
    assert (cell.submitted, cell.rejected, cell.auto_decisions) == (1, 1, 1)
    assert cell.avg_time_to_decision_sec == 1200.0


# --- neighbours that are not there --------------------------------------------------


async def test_works_with_applications_only(
    world: World, session_factory: async_sessionmaker[AsyncSession], facade: OpenFacade
) -> None:
    registry = FacadeRegistry()
    registry.register(ApplicationsFacade, lambda _session: world.applications)
    consumer = Consumer(session_factory, registry)
    app, task_id = uuid4(), uuid4()
    world.card(app, ORG, status="in_review", version=3, updated_at=T0, submitted_at=T0)

    await consumer.deliver(changed(app, "submitted", "in_review"), T0)
    await consumer.deliver(task_created(task_id, app, None), T0 + timedelta(minutes=1))

    async with facade() as projector:
        row = (await projector.list_applications(ORG)).items[0]
        item = (await projector.get_underwriting_queue("underwriter")).items[0]
        dashboard = await projector.get_organization_dashboard(ORG)
    assert row.product_name == "UNSECURED"  # products is not wired: the code stands in
    assert (item.score, item.cash_gap, item.routing_reasons) == (None, False, ())
    assert dashboard is not None and dashboard.pre_approved_max_amount is None


async def test_unknown_application_still_gets_its_history(
    session_factory: async_sessionmaker[AsyncSession], facade: OpenFacade
) -> None:
    consumer = Consumer(session_factory, World().registry)
    app = uuid4()

    await consumer.deliver(changed(app, "submitted", "in_review"), T0)

    async with facade() as projector:
        assert (await projector.list_applications(ORG)).total == 0
        assert len(await projector.get_timeline(app, "client")) == 1


def _envelope(message: Any, at: datetime) -> Envelope:
    return build_envelope(
        message, producer="test", occurred_at=at, correlation_id=message.application_id
    )
