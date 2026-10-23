from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.access.organizations import MemberOrganizationsResolver
from src.core.domain.clock import FrozenClock
from src.core.facades import FacadeRegistry
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.outbox import build_envelope
from src.core.messaging.subscriber import MessageProcessor, Outcome
from src.modules.applications.facade import ApplicationCardDTO, ApplicationsFacade
from src.modules.clients.facade import ClientsFacade, OrganizationSnapshotDTO
from src.modules.decision.facade import DecisionDTO, DecisionFacade, LimitsDTO
from src.modules.identity.facade import IdentityFacade
from src.modules.notifications.infrastructure.database.models import FeedItem
from src.modules.notifications.presentation.consumers import feed_subscriptions
from src.modules.products.facade import ProductsFacade
from src.modules.scoring.facade import ScoringFacade
from tests.fakes import builders
from tests.fakes.applications_facade import FakeApplicationsFacade
from tests.fakes.clients_facade import FakeClientsFacade
from tests.fakes.decision_facade import FakeDecisionFacade
from tests.fakes.identity_facade import FakeIdentityFacade
from tests.fakes.products_facade import FakeProductsFacade
from tests.fakes.scoring_facade import FakeScoringFacade


@dataclass
class World:
    """Fake neighbours on demo data: ООО «Ромашка» (director + accountant) with
    an application, ИП Иванов (owner + the same accountant)."""

    clients: FakeClientsFacade = field(default_factory=FakeClientsFacade)
    applications: FakeApplicationsFacade = field(default_factory=FakeApplicationsFacade)
    products: FakeProductsFacade = field(default_factory=FakeProductsFacade)
    scoring: FakeScoringFacade = field(default_factory=FakeScoringFacade)
    decision: FakeDecisionFacade = field(default_factory=FakeDecisionFacade)
    identity: FakeIdentityFacade = field(default_factory=FakeIdentityFacade)
    director: UUID = field(default_factory=uuid4)
    accountant: UUID = field(default_factory=uuid4)
    ivanov_owner: UUID = field(default_factory=uuid4)
    stranger: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        self.romashka: OrganizationSnapshotDTO = self.clients.add_organization(
            builders.organization_snapshot("romashka")
        )
        self.ivanov: OrganizationSnapshotDTO = self.clients.add_organization(
            builders.organization_snapshot("ivanov")
        )
        self.clients.add_member(self.director, self.romashka.id, "director")
        self.clients.add_member(self.accountant, self.romashka.id, "accountant")
        self.clients.add_member(self.ivanov_owner, self.ivanov.id, "owner")
        self.clients.add_member(self.accountant, self.ivanov.id, "accountant")
        self.products.add_product(builders.product("UNSECURED", name="Кредит без залога"))
        self.products.add_product(builders.product("CREDIT_LINE", name="Кредитная линия"))
        self.card: ApplicationCardDTO = self.applications.add_card(
            builders.application_card(self.romashka, amount=Decimal("3000000"))
        )

    def register(self, registry: FacadeRegistry, *, skip: tuple[type[Any], ...] = ()) -> None:
        pairs: list[tuple[type[Any], Any]] = [
            (ClientsFacade, self.clients),
            (MemberOrganizationsResolver, self.clients),
            (ApplicationsFacade, self.applications),
            (ProductsFacade, self.products),
            (ScoringFacade, self.scoring),
            (DecisionFacade, self.decision),
            (IdentityFacade, self.identity),
        ]
        for key, fake in pairs:
            if key not in skip:
                registry.register(key, lambda _session, fake=fake: fake)


@pytest.fixture
def world() -> World:
    return World()


def decision_with_codes(application_id: UUID, *reason_codes: str) -> DecisionDTO:
    return DecisionDTO(
        id=uuid4(),
        application_id=application_id,
        policy_version="test",
        key_rate=Decimal("16"),
        outcome="REJECT",
        terms=None,
        alternative_product_code=None,
        reason_codes=reason_codes,
        client_explanation="",
        improvement_hints=(),
        requested_info=None,
        rule_trace=(),
        limits=LimitsDTO(None, None, None),
        decided_by_type="underwriter",
        decided_by_id=None,
        override_of=None,
        comment=None,
        decided_at=builders.NOW,
    )


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(builders.NOW)


class RecordingDeadLetters:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    async def publish_dead_letter(self, topic: str, body: dict[str, Any], error: str) -> None:
        self.items.append({"topic": topic, "error": error})


class FeedHarness:
    """Delivers events through the real subscriptions (inbox, transaction) and
    reads what landed in the feed."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        registry: FacadeRegistry,
        clock: FrozenClock,
    ) -> None:
        self.session_factory = session_factory
        self.registry = registry
        self.clock = clock
        self.dead_letters = RecordingDeadLetters()
        self._processor = MessageProcessor(
            session_factory, registry, clock, self.dead_letters, backoff_seconds=(0.0,)
        )

    async def deliver(self, message: IntegrationMessage, event_id: UUID | None = None) -> Outcome:
        subscription = next(s for s in feed_subscriptions() if s.topic == message.TOPIC)
        correlation = getattr(message, "application_id", None) or message.organization_id
        envelope = build_envelope(
            message,
            producer="test",
            occurred_at=self.clock.now(),
            correlation_id=correlation,
            event_id=event_id,
        )
        outcome = await self._processor.process(subscription, envelope.model_dump(mode="json"))
        assert not self.dead_letters.items, self.dead_letters.items
        return outcome

    async def rows(self, **where: Any) -> list[FeedItem]:
        async with self.session_factory() as session:
            stmt = select(FeedItem).filter_by(**where).order_by(FeedItem.seq)
            return list((await session.scalars(stmt)).all())


@pytest.fixture
def registry(world: World) -> FacadeRegistry:
    registry = FacadeRegistry()
    world.register(registry)
    return registry


@pytest.fixture
def feed(
    session_factory: async_sessionmaker[AsyncSession],
    registry: FacadeRegistry,
    clock: FrozenClock,
) -> FeedHarness:
    return FeedHarness(session_factory, registry, clock)
