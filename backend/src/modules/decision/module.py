"""Wiring of the decision module into the application."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from functools import partial

from fastapi import FastAPI

from src.core.messaging import topics
from src.core.messaging.contracts.clients import (
    FinancialReportSubmitted,
    OrganizationVerificationMismatch,
    OrganizationVerified,
)
from src.core.messaging.contracts.decision import (
    CheckStopFactors,
    MakeDecision,
    RecordManualDecision,
)
from src.core.messaging.subscriber import HandlerContext, Subscription
from src.modules.applications.facade import ApplicationsFacade
from src.modules.clients.facade import ClientsFacade
from src.modules.decision.api import policies_router, router
from src.modules.decision.application.check_stop_factors import CheckStopFactorsUseCase
from src.modules.decision.application.input_builder import DecisionInputBuilder
from src.modules.decision.application.make_decision import MakeDecisionUseCase
from src.modules.decision.application.policy_versions import (
    ActivePolicyProvider,
    PolicyProvider,
)
from src.modules.decision.application.pre_approval import RecalculatePreApprovedUseCase
from src.modules.decision.application.record_manual_decision import RecordManualDecisionUseCase
from src.modules.decision.application.refresh_pre_approved import (
    RefreshExpiringPreApprovedUseCase,
)
from src.modules.decision.config import DecisionSettings
from src.modules.decision.domain.policy import CreditPolicy
from src.modules.decision.facade import DecisionFacade
from src.modules.decision.infrastructure.config_loader import (
    CreditPolicyDocuments,
    default_policy,
)
from src.modules.decision.infrastructure.facade_impl import DecisionFacadeImpl
from src.modules.decision.infrastructure.repository import (
    SqlAlchemyDecisionRepository,
    SqlAlchemyFounderPrescreenRepository,
    SqlAlchemyPolicyVersionRepository,
    SqlAlchemyPreApprovedOfferRepository,
)
from src.modules.decision.infrastructure.transaction import SqlAlchemyPreApprovalTransaction
from src.modules.decision.jobs import run_pre_approval_refresh
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.products.facade import ProductsFacade
from src.modules.scoring.facade import ScoringFacade

NAME = "decision"


@dataclass(frozen=True)
class _Runtime:
    policies: PolicyProvider
    key_rate: Decimal
    settings: DecisionSettings


# Встроенная политика грузится один раз на процесс (невалидный YAML → приложение не стартует).
# Решают активной версией админа из БД или встроенной: провайдер спрашивает БД на каждую команду,
# событие и проход ночного пакета. Ключевая ставка и ночной пакет — из DECISION_*.
_runtime: _Runtime | None = None


def register(app: FastAPI) -> None:
    """Pre-approved offers, the founder's prescreen and the project assessment; versions of
    the credit policy for the admin."""
    app.include_router(router)
    app.include_router(policies_router)


def wire(app: FastAPI) -> None:
    global _runtime
    settings = DecisionSettings()
    default_policy()  # невалидный YAML → не стартуем
    _runtime = _Runtime(ActivePolicyProvider(CreditPolicyDocuments()), settings.key_rate, settings)
    # Ручкам — тот же провайдер: собранные версии кэшируются один раз на процесс.
    app.state.decision_policies = _runtime.policies
    clock = app.state.clock
    app.state.facades.register(DecisionFacade, lambda session: DecisionFacadeImpl(session, clock))


async def startup(app: FastAPI) -> None:
    """Ночной пакет предодобрения — вместе с остальными фоновыми задачами."""
    if not app.state.settings.run_background_jobs:
        return
    current = _current()
    clock = app.state.clock
    transactions = partial(
        SqlAlchemyPreApprovalTransaction, app.state.session_factory, app.state.facades, clock
    )
    # Активную политику пакет берёт на каждом проходе, а не один раз при старте.
    use_case = RefreshExpiringPreApprovedUseCase(
        transactions, current.policies, clock, current.key_rate
    )
    stop = asyncio.Event()
    task = asyncio.create_task(
        run_pre_approval_refresh(
            use_case,
            stop,
            interval_seconds=current.settings.pre_approval_refresh_interval_seconds,
            within_days=current.settings.pre_approval_refresh_days,
            first_run_after_seconds=current.settings.pre_approval_refresh_first_run_seconds,
        ),
        name="decision-pre-approval-refresh",
    )
    app.state.decision_jobs = (stop, task)


async def shutdown(app: FastAPI) -> None:
    jobs = getattr(app.state, "decision_jobs", None)
    if jobs is not None:
        stop, task = jobs
        stop.set()
        await task


def _current() -> _Runtime:
    if _runtime is None:
        raise RuntimeError("decision module is not wired")
    return _runtime


async def _policy(ctx: HandlerContext) -> CreditPolicy:
    """Активная политика на эту команду или событие — один запрос в БД."""
    return await _current().policies.active(SqlAlchemyPolicyVersionRepository(ctx.session))


async def _pre_approval(ctx: HandlerContext) -> RecalculatePreApprovedUseCase:
    current = _current()
    return RecalculatePreApprovedUseCase(
        SqlAlchemyPreApprovedOfferRepository(ctx.session),
        await _policy(ctx),
        ctx.facade(ClientsFacade),
        ctx.facade(ProductsFacade),
        ctx.facade(ScoringFacade),
        ctx.clock,
        current.key_rate,
    )


def _builder(ctx: HandlerContext, policy: CreditPolicy) -> DecisionInputBuilder:
    return DecisionInputBuilder(
        policy,
        ctx.facade(ApplicationsFacade),
        ctx.facade(EnrichmentFacade),
        ctx.facade(ScoringFacade),
        ctx.facade(ProductsFacade),
        SqlAlchemyFounderPrescreenRepository(ctx.session),
    )


async def _on_command(
    ctx: HandlerContext, payload: CheckStopFactors | MakeDecision | RecordManualDecision
) -> None:
    current = _current()
    # Каждая команда — активной версией на момент обработки: если политику активировали между
    # CheckStopFactors и MakeDecision одной заявки, они пройдут на разных версиях (она видна в
    # `policy_version` результата).
    policy = await _policy(ctx)
    repository = SqlAlchemyDecisionRepository(ctx.session)
    products = ctx.facade(ProductsFacade)
    event_id = ctx.envelope.event_id
    if isinstance(payload, CheckStopFactors):
        await CheckStopFactorsUseCase(
            repository,
            policy,
            _builder(ctx, policy),
            ctx.clock,
            current.key_rate,
        ).execute(payload, command_event_id=event_id, outbox=ctx.outbox)
    elif isinstance(payload, MakeDecision):
        builder = _builder(ctx, policy)
        await MakeDecisionUseCase(
            repository, policy, builder, products, ctx.clock, current.key_rate
        ).execute(payload, command_event_id=event_id, outbox=ctx.outbox)
    else:
        await RecordManualDecisionUseCase(
            repository,
            policy,
            ctx.facade(ApplicationsFacade),
            products,
            ctx.clock,
            current.key_rate,
        ).execute(payload, command_event_id=event_id, outbox=ctx.outbox)


async def _on_clients_event(
    ctx: HandlerContext,
    payload: FinancialReportSubmitted | OrganizationVerified | OrganizationVerificationMismatch,
) -> None:
    await (await _pre_approval(ctx)).on_event(
        payload.organization_id, event_id=ctx.envelope.event_id, outbox=ctx.outbox
    )


def subscribers() -> list[Subscription]:
    return [
        Subscription(
            module=NAME,
            topic=topics.DECISION_COMMANDS,
            group_id="decision.commands",
            handler=_on_command,
            message_types=frozenset(
                {CheckStopFactors.TYPE, MakeDecision.TYPE, RecordManualDecision.TYPE}
            ),
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
