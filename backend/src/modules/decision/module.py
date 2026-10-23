"""Wiring of the decision module into the application."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from fastapi import FastAPI

from src.core.messaging import topics
from src.core.messaging.contracts.clients import (
    FinancialReportSubmitted,
    OrganizationVerificationMismatch,
    OrganizationVerified,
)
from src.core.messaging.contracts.decision import MakeDecision, RecordManualDecision
from src.core.messaging.subscriber import HandlerContext, Subscription
from src.modules.applications.facade import ApplicationsFacade
from src.modules.clients.facade import ClientsFacade
from src.modules.decision.api import router
from src.modules.decision.application.input_builder import DecisionInputBuilder
from src.modules.decision.application.make_decision import MakeDecisionUseCase
from src.modules.decision.application.pre_approval import RecalculatePreApprovedUseCase
from src.modules.decision.application.record_manual_decision import RecordManualDecisionUseCase
from src.modules.decision.config import DecisionSettings
from src.modules.decision.domain.policy import CreditPolicy
from src.modules.decision.facade import DecisionFacade
from src.modules.decision.infrastructure.config_loader import default_policy
from src.modules.decision.infrastructure.facade_impl import DecisionFacadeImpl
from src.modules.decision.infrastructure.repository import (
    SqlAlchemyDecisionRepository,
    SqlAlchemyFounderPrescreenRepository,
    SqlAlchemyPreApprovedOfferRepository,
)
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.products.facade import ProductsFacade
from src.modules.scoring.facade import ScoringFacade

NAME = "decision"


@dataclass(frozen=True)
class _Runtime:
    policy: CreditPolicy
    key_rate: Decimal


# Политика грузится один раз на процесс (невалидный YAML → приложение не стартует),
# ключевая ставка — из DECISION_KEY_RATE.
_runtime: _Runtime | None = None


def register(app: FastAPI) -> None:
    app.include_router(router)


def wire(app: FastAPI) -> None:
    global _runtime
    _runtime = _Runtime(default_policy(), DecisionSettings().key_rate)
    clock = app.state.clock
    app.state.facades.register(DecisionFacade, lambda session: DecisionFacadeImpl(session, clock))


def _current() -> _Runtime:
    if _runtime is None:
        raise RuntimeError("decision module is not wired")
    return _runtime


def _pre_approval(ctx: HandlerContext) -> RecalculatePreApprovedUseCase:
    current = _current()
    return RecalculatePreApprovedUseCase(
        SqlAlchemyPreApprovedOfferRepository(ctx.session),
        current.policy,
        ctx.facade(ClientsFacade),
        ctx.facade(ProductsFacade),
        ctx.facade(ScoringFacade),
        ctx.clock,
        current.key_rate,
    )


async def _on_command(ctx: HandlerContext, payload: MakeDecision | RecordManualDecision) -> None:
    current = _current()
    repository = SqlAlchemyDecisionRepository(ctx.session)
    products = ctx.facade(ProductsFacade)
    event_id = ctx.envelope.event_id
    if isinstance(payload, MakeDecision):
        builder = DecisionInputBuilder(
            current.policy,
            ctx.facade(ApplicationsFacade),
            ctx.facade(EnrichmentFacade),
            ctx.facade(ScoringFacade),
            products,
            SqlAlchemyFounderPrescreenRepository(ctx.session),
        )
        await MakeDecisionUseCase(
            repository, current.policy, builder, products, ctx.clock, current.key_rate
        ).execute(payload, command_event_id=event_id, outbox=ctx.outbox)
    else:
        await RecordManualDecisionUseCase(
            repository,
            current.policy,
            ctx.facade(ApplicationsFacade),
            products,
            ctx.clock,
            current.key_rate,
        ).execute(payload, command_event_id=event_id, outbox=ctx.outbox)


async def _on_clients_event(
    ctx: HandlerContext,
    payload: FinancialReportSubmitted | OrganizationVerified | OrganizationVerificationMismatch,
) -> None:
    await _pre_approval(ctx).on_event(
        payload.organization_id, event_id=ctx.envelope.event_id, outbox=ctx.outbox
    )


def subscribers() -> list[Subscription]:
    return [
        Subscription(
            module=NAME,
            topic=topics.DECISION_COMMANDS,
            group_id="decision.commands",
            handler=_on_command,
            message_types=frozenset({MakeDecision.TYPE, RecordManualDecision.TYPE}),
        ),
        Subscription(
            module=NAME,
            topic=topics.CLIENTS_EVENTS,
            group_id="decision.clients-events",
            handler=_on_clients_event,
            # A check against the registry may change the status or the head:
            # the pre-approval follows either outcome.
            message_types=frozenset(
                {
                    FinancialReportSubmitted.TYPE,
                    OrganizationVerified.TYPE,
                    OrganizationVerificationMismatch.TYPE,
                }
            ),
        ),
    ]
