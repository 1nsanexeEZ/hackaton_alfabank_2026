"""Decision в настоящем приложении: подписки модуля, inbox/outbox, API предодобрений.

Соседи — фейки мира golden-тестов (S-1, «Ромашка»), сообщения — в ручном режиме: команду или
событие кладём в outbox от имени отправителя и доставляем `drain()` через подписки модулей.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.core.access.permissions import Permissions
from src.core.config import Settings
from src.core.domain.clock import FrozenClock
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.contracts.clients import (
    Discrepancy,
    FinancialReportSubmitted,
    OrganizationVerificationMismatch,
    OrganizationVerified,
)
from src.core.messaging.contracts.decision import MakeDecision
from src.core.messaging.outbox import OutboxRecord, SqlAlchemyOutboxWriter
from src.core.messaging.subscriber import MessageProcessor
from src.main import create_app
from src.modules.applications.facade import ApplicationsFacade
from src.modules.clients.facade import ClientsFacade
from src.modules.decision import module as decision_module
from src.modules.decision.facade import DecisionFacade
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.products.facade import ProductsFacade
from src.modules.scoring.facade import ScoringFacade
from tests.decision.unit.decision_world import NOW, DecisionWorld, build_world
from tests.fakes import builders, install
from tests.fakes.clients_facade import FakeClientsFacade
from tests.helpers import bearer, create_schema, token_for

OWNER = UUID("00000000-0000-4000-8000-000000000001")
STRANGER = UUID("00000000-0000-4000-8000-000000000002")
CLIENT_POLICIES = {Permissions.ORGANIZATIONS_READ: ["org_member"]}


@dataclass
class App:
    client: TestClient
    world: DecisionWorld

    def run(self, fn: Any, *args: Any) -> Any:
        return self.client.portal.call(fn, *args)  # type: ignore[union-attr]

    def send(self, message: IntegrationMessage, key: UUID, producer: str) -> UUID:
        clock = self.client.app.state.clock  # type: ignore[attr-defined]

        async def stage() -> UUID:
            async with self.client.app.state.session_factory() as session:  # type: ignore[attr-defined]
                event_id = await SqlAlchemyOutboxWriter(session, producer, clock).add(
                    message, key=key, correlation_id=key
                )
                await session.commit()
                return event_id

        event_id: UUID = self.run(stage)
        self.run(self.client.app.state.messaging.drain)  # type: ignore[attr-defined]
        return event_id

    def envelopes(self, message_type: str) -> list[dict[str, Any]]:
        async def read() -> list[dict[str, Any]]:
            async with self.client.app.state.session_factory() as session:  # type: ignore[attr-defined]
                stmt = (
                    select(OutboxRecord)
                    .where(OutboxRecord.message_type == message_type)
                    .order_by(OutboxRecord.id)
                )
                return [record.envelope for record in await session.scalars(stmt)]

        return self.run(read)

    def get(self, path: str, *, permissions: list[Permissions], subject: UUID, **kw: Any) -> Any:
        token = token_for(self.client.app, permissions, kw.get("policies"), subject)  # type: ignore[arg-type]
        return self.client.get(path, headers=bearer(token))

    def offers_path(self) -> str:
        return f"/organizations/{self.world.organization_id}/pre-approved-offers"

    def offers(self) -> list[dict[str, Any]]:
        response = self.get(
            self.offers_path(),
            permissions=[Permissions.ORGANIZATIONS_READ],
            policies=CLIENT_POLICIES,
            subject=OWNER,
        )
        assert response.status_code == 200, response.text
        offers: list[dict[str, Any]] = response.json()
        return offers


@pytest.fixture
def app(settings: Settings) -> Iterator[App]:
    world = asyncio.run(build_world("s1_romashka", acts_for_itself=True))
    clients = FakeClientsFacade()
    clients.add_organization(
        builders.organization_snapshot("romashka", organization_id=world.organization_id)
    )
    clients.add_member(OWNER, world.organization_id, "owner")
    application = create_app(settings, clock=FrozenClock(NOW))
    install(application, ApplicationsFacade, world.applications)
    install(application, EnrichmentFacade, world.enrichment)
    install(application, ScoringFacade, world.scoring)
    install(application, ProductsFacade, world.products)
    install(application, ClientsFacade, clients)
    create_schema(settings.database_url)
    with TestClient(application) as client:
        yield App(client, world)


def test_make_decision_through_the_subscription(app: App) -> None:
    application_id = app.world.application_id

    command_id = app.send(MakeDecision(application_id=application_id), application_id, "process")

    [reply] = app.envelopes("DecisionMade")
    assert reply["producer"] == "decision"
    assert reply["causation_id"] == str(command_id)
    assert reply["correlation_id"] == str(application_id)
    payload = reply["payload"]
    assert payload["outcome"] == "APPROVE" and payload["decided_by"] == "auto"
    assert payload["offer"]["amount"] == "3000000" and payload["offer"]["rate"] == "23.50"
    assert payload["offer"]["monthly_payment"] == "157865.62"

    async def bank_view() -> Any:
        async with app.client.app.state.session_factory() as session:  # type: ignore[attr-defined]
            facade = app.client.app.state.facades.get(DecisionFacade, session)  # type: ignore[attr-defined]
            return await facade.get_decision(application_id)

    stored = app.run(bank_view)
    assert stored is not None and str(stored.id) == payload["decision_id"]


def test_redelivered_command_is_processed_once(app: App) -> None:
    application_id = app.world.application_id
    app.send(MakeDecision(application_id=application_id), application_id, "process")
    [envelope] = [
        e
        for e in app.envelopes("MakeDecision")
        if e["payload"]["application_id"] == str(application_id)
    ]
    [commands] = [s for s in decision_module.subscribers() if s.group_id == "decision.commands"]
    state = app.client.app.state  # type: ignore[attr-defined]
    processor = MessageProcessor(
        state.session_factory, state.facades, state.clock, state.messaging.bus
    )

    outcome = app.run(processor.process, commands, envelope)

    assert outcome == "duplicate"
    assert len(app.envelopes("DecisionMade")) == 1


@pytest.mark.parametrize("event", [FinancialReportSubmitted, OrganizationVerified])
def test_clients_events_recalculate_pre_approved_offers(app: App, event: Any) -> None:
    organization_id = app.world.organization_id
    message = (
        event(organization_id=organization_id, period_year=2025)
        if event is FinancialReportSubmitted
        else event(organization_id=organization_id)
    )

    event_id = app.send(message, organization_id, "clients")

    [updated] = app.envelopes("PreApprovedOffersUpdated")
    assert updated["payload"] == {"organization_id": str(organization_id)}
    assert updated["causation_id"] == str(event_id)
    response = app.get(
        app.offers_path(),
        permissions=[Permissions.ORGANIZATIONS_READ],
        policies=CLIENT_POLICIES,
        subject=OWNER,
    )
    assert response.status_code == 200, response.text
    offers = response.json()
    assert offers and {"UNSECURED", "OVERDRAFT"} <= {o["product_code"] for o in offers}
    amounts = [float(o["max_amount"]) for o in offers]
    assert amounts == sorted(amounts, reverse=True)
    first = offers[0]
    assert first["basis"] == "estimate" and first["valid_until"] == "2026-11-20"
    assert "окончательное решение" in first["note"]
    assert "factors_summary" not in first


def test_registry_mismatch_event_removes_offers(app: App) -> None:
    organization_id = app.world.organization_id
    app.send(
        FinancialReportSubmitted(organization_id=organization_id, period_year=2025),
        organization_id,
        "clients",
    )
    assert app.offers()
    clients: FakeClientsFacade = app.client.app.state.facades.get(ClientsFacade, None)  # type: ignore[attr-defined]
    snapshot = clients.organizations[organization_id]
    clients.add_organization(replace(snapshot, verification_status="mismatch"))

    event_id = app.send(
        OrganizationVerificationMismatch(
            organization_id=organization_id,
            discrepancies=[Discrepancy(field="head_name", declared="Петров П. П.")],
        ),
        organization_id,
        "clients",
    )

    assert app.offers() == []
    updated = app.envelopes("PreApprovedOffersUpdated")
    assert len(updated) == 2 and updated[-1]["causation_id"] == str(event_id)


def test_pre_approved_offers_access(app: App) -> None:
    organization_id = app.world.organization_id
    app.send(
        FinancialReportSubmitted(organization_id=organization_id, period_year=2025),
        organization_id,
        "clients",
    )
    path = app.offers_path()

    stranger = app.get(
        path,
        permissions=[Permissions.ORGANIZATIONS_READ],
        policies=CLIENT_POLICIES,
        subject=STRANGER,
    )
    without_permission = app.get(path, permissions=[Permissions.REQUESTS_READ], subject=OWNER)
    bank_staff = app.get(path, permissions=[Permissions.ORGANIZATIONS_READ], subject=uuid4())
    anonymous = app.client.get(path)

    assert stranger.status_code == 404
    assert without_permission.status_code == 403
    assert anonymous.status_code == 401
    assert bank_staff.status_code == 200 and bank_staff.json()


def test_no_offers_yet_is_an_empty_list(app: App) -> None:
    response = app.get(
        app.offers_path(),
        permissions=[Permissions.ORGANIZATIONS_READ],
        policies=CLIENT_POLICIES,
        subject=OWNER,
    )

    assert response.status_code == 200 and response.json() == []
