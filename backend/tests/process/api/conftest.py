"""The whole pipeline in one process: real applications and process modules,
the messages go through the same subscriptions as in Kafka; enrichment,
scoring and decision are played by responders on their command topics."""

from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.core.access.permissions import Permissions
from src.core.config import Settings
from src.core.messaging import topics
from src.core.messaging.contracts.applications import OfferTerms
from src.core.messaging.contracts.decision import (
    DecisionMade,
    MakeDecision,
    RecordManualDecision,
    RequestedInfo,
)
from src.core.messaging.contracts.enrichment import EnrichmentCompleted, FetchEnrichment
from src.core.messaging.contracts.scoring import CalculateScore, ScoreCalculated
from src.core.messaging.runtime import MessagingRuntime
from src.core.messaging.subscriber import HandlerContext, Subscription
from src.modules.applications.infrastructure.consumers import (
    subscriptions as application_subscriptions,
)
from src.modules.process.infrastructure.consumers import subscriptions as process_subscriptions
from tests.applications.api.conftest import World, world  # noqa: F401  shared fixture
from tests.helpers import bearer, token_for


@dataclass
class Responders:
    """What the neighbours answer; `hold` — the module stays silent."""

    decisions: deque[str] = field(default_factory=deque)
    hold: set[str] = field(default_factory=set)
    received: list[str] = field(default_factory=list)


@dataclass
class Pipeline:
    world: World
    runtime: MessagingRuntime
    responders: Responders

    def drain(self) -> None:
        self.world.run(self.runtime.drain)

    def underwriter(self) -> dict[str, str]:
        token = token_for(
            self.world.client.app,  # type: ignore[arg-type]
            [Permissions.TASKS_READ, Permissions.TASKS_UPDATE, Permissions.REQUESTS_READ],
            {},
            UNDERWRITER,
        )
        return bearer(token)

    def card(self, application_id: str) -> dict[str, Any]:
        return self.world.client.get(
            f"/applications/{application_id}", headers=self.world.headers(self.world.director)
        ).json()

    def process(self, application_id: str) -> dict[str, Any]:
        response = self.world.client.get(f"/processes/{application_id}", headers=self.underwriter())
        assert response.status_code == 200, response.text
        return response.json()

    def submit(self) -> str:
        application = self.world.submit(self.world.ready())
        self.drain()
        return application["id"]

    @property
    def dead_letters(self) -> list[dict]:
        assert self.runtime.bus is not None
        return self.runtime.bus.dead_letters


UNDERWRITER = UUID("00000000-0000-0000-0000-0000000000ff")


def offer_terms(target: World, kind: str = "as_requested", amount: str = "3000000") -> OfferTerms:
    return OfferTerms(
        kind=kind,  # type: ignore[arg-type]
        amount=Decimal(amount),
        term_months=24,
        rate=Decimal("23.5"),
        monthly_payment=Decimal("158000"),
        conditions=[],
        expires_at=target.clock.now() + timedelta(days=7),
    )


def responder_subscriptions(target: World, responders: Responders) -> list[Subscription]:
    async def enrichment(ctx: HandlerContext, command: FetchEnrichment) -> None:
        responders.received.append("FetchEnrichment")
        if "enrichment" in responders.hold:
            return
        await ctx.outbox.add(
            EnrichmentCompleted(
                application_id=command.application_id,
                snapshot_id=uuid4(),
                sources_ok=["egrul", "fns", "bki"],
                cash_gap_detected=False,
            ),
            key=command.application_id,
            correlation_id=command.application_id,
            causation_id=ctx.envelope.event_id,
        )

    async def scoring(ctx: HandlerContext, command: CalculateScore) -> None:
        responders.received.append("CalculateScore")
        await ctx.outbox.add(
            ScoreCalculated(
                application_id=command.application_id,
                result_id=uuid4(),
                score=790,
                risk_grade="A",
            ),
            key=command.application_id,
            correlation_id=command.application_id,
            causation_id=ctx.envelope.event_id,
        )

    async def decision(ctx: HandlerContext, command: MakeDecision | RecordManualDecision) -> None:
        responders.received.append(command.TYPE)
        manual = isinstance(command, RecordManualDecision)
        outcome = command.outcome if manual else responders.decisions.popleft()
        offer = None
        if outcome in ("APPROVE", "COUNTER_OFFER"):
            amount = str(command.terms.amount) if manual and command.terms else "3000000"
            kind = "as_requested" if outcome == "APPROVE" else "counter"
            offer = offer_terms(target, kind, amount)
        requested = None
        if outcome == "REQUEST_INFO":
            requested = RequestedInfo(
                documents=["financial_statement"], comment="Отчётность за год"
            )
        await ctx.outbox.add(
            DecisionMade(
                application_id=command.application_id,
                decision_id=uuid4(),
                outcome=outcome,  # type: ignore[arg-type]
                offer=offer,
                decided_by="underwriter" if manual else "auto",
                requested_info=requested,
                client_explanation="Пояснение для клиента",
            ),
            key=command.application_id,
            correlation_id=command.application_id,
            causation_id=ctx.envelope.event_id,
        )

    return [
        Subscription("enrichment", topics.ENRICHMENT_COMMANDS, "test.enrichment", enrichment),
        Subscription("scoring", topics.SCORING_COMMANDS, "test.scoring", scoring),
        Subscription("decision", topics.DECISION_COMMANDS, "test.decision", decision),
    ]


@pytest.fixture
def pipeline(world: World, settings: Settings) -> Iterator[Pipeline]:  # noqa: F811
    # Every product of the fake catalog runs on the express route.
    for code, product in world.products.products.items():
        world.products.products[code] = replace(product, workflow_code="express_v1")
    app = world.client.app
    responders = Responders()
    runtime = MessagingRuntime(
        settings,
        app.state.session_factory,  # type: ignore[attr-defined]
        app.state.facades,  # type: ignore[attr-defined]
        world.clock,
        [
            *application_subscriptions(),
            *process_subscriptions(),
            *responder_subscriptions(world, responders),
        ],
    )
    world.run(runtime.start)
    yield Pipeline(world, runtime, responders)
    world.run(runtime.stop)
