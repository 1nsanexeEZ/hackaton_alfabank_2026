"""Kafka entry points of the engine and the timeout job.

One consumer group per topic (`process.<topic>`): applications events start,
move and cancel processes; replies of enrichment, scoring and decision are
matched to the command by `causation_id`.
"""

import asyncio
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from src.applications.facade import ApplicationsFacade
from src.core.domain.clock import Clock
from src.core.facades import FacadeRegistry
from src.core.messaging import topics
from src.core.messaging.contracts import applications as app_events
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.outbox import OutboxWriter, SqlAlchemyOutboxWriter
from src.core.messaging.subscriber import HandlerContext, Subscription
from src.process.application.ports import WorkflowSource
from src.process.application.service import ProcessService
from src.process.domain.steps import Trigger
from src.process.infrastructure.facts import ApplicationFacts
from src.process.infrastructure.repository import (
    SqlAlchemyProcessRepository,
    SqlAlchemyTaskRepository,
)
from src.products.facade import ProductsFacade

logger = logging.getLogger(__name__)

MODULE = "process"

CLIENT_EVENTS = frozenset(
    {
        app_events.ApplicationInfoProvided.TYPE,
        app_events.OfferAccepted.TYPE,
        app_events.OfferDeclined.TYPE,
        app_events.OfferExpired.TYPE,
        app_events.ApplicationSigned.TYPE,
    }
)
REPLIES = {
    topics.ENRICHMENT_EVENTS: frozenset({"EnrichmentCompleted", "EnrichmentFailed"}),
    topics.SCORING_EVENTS: frozenset({"ScoreCalculated", "ScoringFailed"}),
    topics.DECISION_EVENTS: frozenset({"DecisionMade", "ManualDecisionRejected"}),
}


def build_service(
    session: AsyncSession,
    outbox: OutboxWriter,
    facades: FacadeRegistry,
    workflows: WorkflowSource,
    clock: Clock,
    with_products: bool = False,
) -> ProcessService:
    return ProcessService(
        processes=SqlAlchemyProcessRepository(session),
        tasks=SqlAlchemyTaskRepository(session),
        outbox=outbox,
        workflows=workflows,
        facts=ApplicationFacts(facades.get(ApplicationsFacade, session)),
        products=facades.get(ProductsFacade, session) if with_products else None,
        clock=clock,
    )


def _service(ctx: HandlerContext, with_products: bool = False) -> ProcessService:
    return build_service(
        ctx.session,
        ctx.outbox,
        ctx.facades,
        ctx.facade(WorkflowSource),  # registered by process.module.wire
        ctx.clock,
        with_products,
    )


async def handle_application_event(ctx: HandlerContext, event: IntegrationMessage) -> None:
    payload: Any = event
    causation = ctx.envelope.event_id
    if isinstance(event, app_events.ApplicationSubmitted):
        await _service(ctx, with_products=True).start(
            event.application_id, event.organization_id, event.product_code, causation
        )
    elif isinstance(event, app_events.ApplicationCancelled):
        await _service(ctx).cancel(event.application_id, causation)
    else:
        await _service(ctx).handle(
            payload.application_id, Trigger(event.TYPE, event.model_dump()), causation
        )


async def handle_reply(ctx: HandlerContext, reply: IntegrationMessage) -> None:
    application_id = reply.application_id  # type: ignore[attr-defined]
    trigger = Trigger(reply.TYPE, reply.model_dump(), causation_id=ctx.envelope.causation_id)
    await _service(ctx).handle(application_id, trigger, ctx.envelope.event_id)


def subscriptions() -> list[Subscription]:
    started_by = {app_events.ApplicationSubmitted.TYPE, app_events.ApplicationCancelled.TYPE}
    return [
        Subscription(
            MODULE,
            topics.APPLICATIONS_EVENTS,
            "process.applications-events",
            handle_application_event,
            message_types=frozenset(started_by | CLIENT_EVENTS),
        ),
        *(
            Subscription(MODULE, topic, f"process.{topic.replace('.', '-')}", handle_reply, types)
            for topic, types in REPLIES.items()
        ),
    ]


async def time_out_stuck_steps(
    session_factory: async_sessionmaker[AsyncSession],
    facades: FacadeRegistry,
    workflows: WorkflowSource,
    clock: Clock,
    min_wait: timedelta = timedelta(seconds=30),
    batch_size: int = 100,
) -> int:
    """Processes waiting for a reply too long: one transaction per application."""
    async with session_factory() as session:
        candidates = await SqlAlchemyProcessRepository(session).waiting_for_replies_since(
            clock.now() - min_wait, batch_size
        )
    timed_out = 0
    for application_id in candidates:
        async with session_factory() as session:
            service = build_service(
                session, SqlAlchemyOutboxWriter(session, MODULE, clock), facades, workflows, clock
            )
            try:
                if await service.time_out(application_id):
                    await session.commit()
                    timed_out += 1
            except StaleDataError:
                await session.rollback()
    return timed_out


async def run_timeouts(
    session_factory: async_sessionmaker[AsyncSession],
    facades: FacadeRegistry,
    workflows: WorkflowSource,
    clock: Clock,
    stop: asyncio.Event,
    interval_seconds: float = 30,
) -> None:
    while not stop.is_set():
        try:
            count = await time_out_stuck_steps(session_factory, facades, workflows, clock)
            if count:
                logger.warning("%s process steps timed out", count)
        except Exception:
            logger.exception("Process timeout run failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass
