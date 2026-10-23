"""Wiring: subscriptions, the facade in the registry, the whole flow inside the app."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from src.core.messaging import topics
from src.core.messaging.contracts.applications import ApplicationSubmitted
from src.core.messaging.outbox import SqlAlchemyOutboxWriter
from src.core.messaging.runtime import validate_subscriptions
from src.modules.applications.facade import ApplicationsFacade
from src.modules.products.facade import ProductsFacade
from src.modules.projector import module
from src.modules.projector.facade import ProjectorFacade
from src.modules.projector.infrastructure.facade_impl import ProjectorFacadeImpl
from tests.fakes import install
from tests.projector.world import World

AT = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


def test_one_consumer_group_per_projected_topic() -> None:
    subscriptions = module.subscribers()
    validate_subscriptions(subscriptions)
    assert {s.topic for s in subscriptions} == {
        topics.APPLICATIONS_EVENTS,
        topics.PROCESS_EVENTS,
        topics.DECISION_EVENTS,
        topics.CLIENTS_EVENTS,
    }
    assert sorted(s.group_id for s in subscriptions) == [
        "projector.read-models.applications",
        "projector.read-models.clients",
        "projector.read-models.decision",
        "projector.read-models.process",
    ]
    assert all(s.module == "projector" and s.message_types is None for s in subscriptions)


def test_wire_registers_the_facade(client: TestClient) -> None:
    app = client.app
    assert app.state.facades.has(ProjectorFacade)  # type: ignore[attr-defined]


def test_event_from_the_outbox_reaches_the_read_models(client: TestClient) -> None:
    app = client.app
    state = app.state  # type: ignore[attr-defined]
    world = World()
    install(app, ApplicationsFacade, world.applications)  # type: ignore[arg-type]
    install(app, ProductsFacade, world.products)  # type: ignore[arg-type]
    organization_id, application_id = uuid4(), uuid4()
    world.card(application_id, organization_id, updated_at=AT, submitted_at=AT)

    async def publish_and_read() -> tuple[int, str]:
        async with state.session_factory() as session:
            await SqlAlchemyOutboxWriter(session, "applications", state.clock).add(
                ApplicationSubmitted(
                    application_id=application_id,
                    organization_id=organization_id,
                    product_code="UNSECURED",
                    amount=Decimal("3000000"),
                    term_months=24,
                    purpose="working_capital",
                ),
                key=application_id,
                correlation_id=application_id,
            )
            await session.commit()
        await state.messaging.drain()
        async with state.session_factory() as session:
            projector = state.facades.get(ProjectorFacade, session)
            assert isinstance(projector, ProjectorFacadeImpl)
            page = await projector.list_applications(organization_id)
        return page.total, page.items[0].product_name

    assert client.portal.call(publish_and_read) == (1, "Кредит без залога")  # type: ignore[union-attr]
    assert state.messaging.bus.dead_letters == []
