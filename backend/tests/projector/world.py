"""What the projector sees around itself in tests: fake neighbours, DTO
builders for them, delivery of events through the real consumer and a
JSON-friendly dump of every read model table."""

from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import AbstractAsyncContextManager
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.domain.clock import FrozenClock
from src.core.facades import FacadeRegistry
from src.core.messaging.contracts.base import IntegrationMessage, get_contract
from src.core.messaging.outbox import build_envelope
from src.core.messaging.subscriber import MessageProcessor, Outcome, Subscription
from src.modules.applications.facade import ApplicationCardDTO, ApplicationsFacade, OfferDTO
from src.modules.clients.facade import ClientsFacade
from src.modules.decision.facade import DecisionDTO, DecisionFacade, LimitsDTO, PreApprovedOfferDTO
from src.modules.process.facade import ProcessFacade, UserTaskDTO
from src.modules.products.facade import ProductsFacade
from src.modules.projector import module as projector_module
from src.modules.projector.infrastructure.facade_impl import ProjectorFacadeImpl
from src.modules.projector.infrastructure.repositories import ALL_ROWS, SqlAlchemyReadModelStore
from src.modules.scoring.facade import ScoringFacade, ScoringResultDTO
from tests.fakes import builders
from tests.fakes.applications_facade import FakeApplicationsFacade
from tests.fakes.clients_facade import FakeClientsFacade
from tests.fakes.decision_facade import FakeDecisionFacade
from tests.fakes.process_facade import FakeProcessFacade
from tests.fakes.products_facade import FakeProductsFacade
from tests.fakes.scoring_facade import FakeScoringFacade

# Fixtures `facade` and `store`: `async with facade() as projector: ...`
OpenFacade = Callable[[], AbstractAsyncContextManager[ProjectorFacadeImpl]]
OpenStore = Callable[[], AbstractAsyncContextManager[SqlAlchemyReadModelStore]]

_NAMESPACE = UUID("0b5c2f7e-3d61-4b8a-9e0f-5a4c7d2e1f30")
APPLICANT = UUID("00000000-0000-4000-8000-0000000000a1")

PRODUCT_NAMES = {
    "UNSECURED": "Кредит без залога",
    "CREDIT_LINE": "Кредитная линия",
    "OVERDRAFT": "Овердрафт",
}


def uid(name: str) -> UUID:
    """Stable ids: golden files compare them."""
    return uuid5(_NAMESPACE, name)


class World:
    """Fake neighbours of the projector, registered in one facade registry."""

    def __init__(self) -> None:
        self.applications = FakeApplicationsFacade()
        self.products = FakeProductsFacade()
        self.process = FakeProcessFacade()
        self.scoring = FakeScoringFacade()
        self.decision = FakeDecisionFacade()
        self.clients = FakeClientsFacade()
        self.registry = FacadeRegistry()
        pairs: list[tuple[type[Any], Any]] = [
            (ApplicationsFacade, self.applications),
            (ProductsFacade, self.products),
            (ProcessFacade, self.process),
            (ScoringFacade, self.scoring),
            (DecisionFacade, self.decision),
            (ClientsFacade, self.clients),
        ]
        for key, fake in pairs:
            self.registry.register(key, lambda _session, fake=fake: fake)
        for code, name in PRODUCT_NAMES.items():
            self.products.add_product(builders.product(code, name=name))

    def card(
        self,
        application_id: UUID,
        organization_id: UUID,
        *,
        company: str = "romashka",
        number: str = "КР-2026-000001",
        product_code: str = "UNSECURED",
        amount: Decimal = Decimal("3000000"),
        term_months: int = 24,
        status: str = "submitted",
        version: int = 2,
        updated_at: datetime,
        submitted_at: datetime | None = None,
        client_stage: str | None = None,
        offer: OfferDTO | None = None,
    ) -> ApplicationCardDTO:
        """Put the current state of an application into the applications fake."""
        snapshot = builders.organization_snapshot(company, organization_id=organization_id)
        card = builders.application_card(
            snapshot,
            amount=amount,
            term_months=term_months,
            status=status,
            id=application_id,
            number=number,
            product_code=product_code,
            applicant_account_id=APPLICANT,
            client_stage=client_stage,
            offer=offer,
            version=version,
            created_at=updated_at if submitted_at is None else submitted_at,
            updated_at=updated_at,
            submitted_at=submitted_at,
        )
        return self.applications.add_card(card)

    def update_card(self, application_id: UUID, **changes: Any) -> ApplicationCardDTO:
        card = self.applications.cards[application_id]
        return self.applications.add_card(replace(card, **changes))


def offer(
    amount: str,
    rate: str,
    decision_id: UUID,
    expires_at: datetime,
    kind: str = "as_requested",
    term_months: int = 24,
) -> OfferDTO:
    return OfferDTO(
        kind=kind,  # type: ignore[arg-type]
        amount=Decimal(amount),
        term_months=term_months,
        rate=Decimal(rate),
        monthly_payment=Decimal("158613.29"),
        schedule_type="annuity",
        conditions=(),
        expires_at=expires_at,
        decision_id=decision_id,
    )


def task(
    task_id: UUID,
    application_id: UUID,
    *,
    created_at: datetime,
    status: str = "open",
    due_at: datetime | None = None,
    assignee_id: UUID | None = None,
    role: str = "underwriter",
    task_type: str = "manual_review",
    process_id: UUID | None = None,
) -> UserTaskDTO:
    return UserTaskDTO(
        id=task_id,
        process_id=process_id or uid(f"process-of-{application_id}"),
        application_id=application_id,
        node_id="underwriter_review",
        type=task_type,
        candidate_role=role,
        assignee_id=assignee_id,
        status=status,  # type: ignore[arg-type]
        form_schema={},
        created_at=created_at,
        due_at=due_at,
        completed_by=assignee_id if status == "done" else None,
    )


def scoring_result(
    application_id: UUID,
    score: int,
    grade: str,
    flags: tuple[str, ...] = (),
    computed_at: datetime | None = None,
) -> ScoringResultDTO:
    return ScoringResultDTO(
        id=uid(f"scoring-of-{application_id}"),
        application_id=application_id,
        model_version="scorecard-v1",
        score=score,
        grade=grade,  # type: ignore[arg-type]
        factors=(),
        flags=flags,
        data_completeness=Decimal("0.9"),
        computed_at=computed_at or builders.NOW,
    )


def decision(
    application_id: UUID,
    outcome: str,
    *,
    decided_at: datetime,
    decided_by: str = "auto",
    reason_codes: tuple[str, ...] = (),
    decision_id: UUID | None = None,
) -> DecisionDTO:
    return DecisionDTO(
        id=decision_id or uuid4(),
        application_id=application_id,
        policy_version="policy-2026.10",
        key_rate=Decimal("21"),
        outcome=outcome,  # type: ignore[arg-type]
        terms=None,
        alternative_product_code=None,
        reason_codes=reason_codes,
        client_explanation="Пояснение для клиента",
        improvement_hints=(),
        requested_info=None,
        rule_trace=(),
        limits=LimitsDTO(by_revenue=None, by_ltv=None, by_capacity=None),
        decided_by_type=decided_by,  # type: ignore[arg-type]
        decided_by_id=None,
        override_of=None,
        comment=None,
        decided_at=decided_at,
    )


def pre_approved(product_code: str, max_amount: str, rate_from: str) -> PreApprovedOfferDTO:
    return PreApprovedOfferDTO(
        product_code=product_code,
        max_amount=Decimal(max_amount),
        rate_from=Decimal(rate_from),
        term_max_months=36,
        valid_until=date(2026, 12, 31),
        basis="Обороты по счёту",
    )


# --- messages -----------------------------------------------------------------


def envelope(
    message: IntegrationMessage, at: datetime, event_id: UUID | None = None
) -> dict[str, Any]:
    key = getattr(message, "application_id", None) or getattr(message, "organization_id", None)
    assert isinstance(key, UUID)
    return build_envelope(
        message,
        producer="test",
        occurred_at=at,
        correlation_id=key,
        event_id=event_id or uuid4(),
    ).model_dump(mode="json")


class DeadLetters:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    async def publish_dead_letter(self, topic: str, body: dict[str, Any], error: str) -> None:
        self.items.append({"topic": topic, "error": error, "type": body.get("type")})


async def _no_sleep(_seconds: float) -> None:
    return None


class Consumer:
    """The live path: projector subscriptions behind the core MessageProcessor
    (parsing, inbox, one transaction per event)."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        registry: FacadeRegistry,
    ) -> None:
        self.dead_letters = DeadLetters()
        self.processor = MessageProcessor(
            session_factory,
            registry,
            FrozenClock(),
            self.dead_letters,
            backoff_seconds=(0.0,),
            sleep=_no_sleep,
        )
        self.subscriptions: dict[str, Subscription] = {
            s.topic: s for s in projector_module.subscribers()
        }

    async def deliver(
        self, message: IntegrationMessage, at: datetime, event_id: UUID | None = None
    ) -> Outcome:
        return await self.deliver_envelope(envelope(message, at, event_id))

    async def deliver_envelope(self, body: dict[str, Any]) -> Outcome:
        outcome = await self.processor.process(self.subscriptions[body_topic(body)], body)
        assert self.dead_letters.items == [], self.dead_letters.items
        return outcome


def body_topic(body: dict[str, Any]) -> str:
    return get_contract(body["type"]).TOPIC


async def stream(bodies: Iterable[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
    for body in bodies:
        yield body


# --- table dump -----------------------------------------------------------------


def _plain(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=UTC)
        return moment.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in sorted(value.items())}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    return value


async def dump_tables(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """Every projector table, rows ordered by primary key, values as JSON."""
    result: dict[str, Any] = {}
    async with session_factory() as session:
        for model in ALL_ROWS:
            table = model.__table__
            stmt = select(table).order_by(*table.primary_key.columns)
            rows = (await session.execute(stmt)).mappings().all()
            result[table.name] = [{k: _plain(v) for k, v in row.items()} for row in rows]
    return result


def minutes(base: datetime, value: float) -> datetime:
    return base + timedelta(minutes=value)
