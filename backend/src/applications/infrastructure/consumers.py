"""Kafka entry points of the module and the offer expiry job."""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from src.applications.application.commands import CommandService
from src.applications.application.ports import AbsClient
from src.applications.infrastructure.repository import SqlAlchemyApplicationRepository
from src.core.domain.clock import Clock
from src.core.messaging import topics
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.contracts.process import StepCompleted
from src.core.messaging.outbox import SqlAlchemyOutboxWriter
from src.core.messaging.subscriber import HandlerContext, Subscription

logger = logging.getLogger(__name__)

MODULE = "applications"


async def handle_command(ctx: HandlerContext, command: IntegrationMessage) -> None:
    service = CommandService(
        SqlAlchemyApplicationRepository(ctx.session), ctx.outbox, ctx.clock, ctx.facade(AbsClient)
    )
    await service.handle(command, ctx.envelope.event_id)


async def handle_step_completed(ctx: HandlerContext, event: StepCompleted) -> None:
    """The stage label shown to the client ("Проверяем данные о компании")."""
    service = CommandService(SqlAlchemyApplicationRepository(ctx.session), ctx.outbox, ctx.clock)
    await service.set_client_stage(event.application_id, event.client_stage)


def subscriptions() -> list[Subscription]:
    return [
        Subscription(MODULE, topics.APPLICATIONS_COMMANDS, "applications.commands", handle_command),
        Subscription(
            MODULE,
            topics.PROCESS_EVENTS,
            "applications.process-events",
            handle_step_completed,
            message_types=frozenset({StepCompleted.TYPE}),
        ),
    ]


async def expire_offers(
    session_factory: async_sessionmaker[AsyncSession], clock: Clock, batch_size: int = 100
) -> int:
    """Move overdue offers to EXPIRED, one transaction per application, so a
    client accepting at the same moment only makes us skip that one."""
    async with session_factory() as session:
        due = await SqlAlchemyApplicationRepository(session).offers_expired_by(
            clock.now(), batch_size
        )
    expired = 0
    for application_id in due:
        async with session_factory() as session:
            service = CommandService(
                SqlAlchemyApplicationRepository(session),
                SqlAlchemyOutboxWriter(session, MODULE, clock),
                clock,
            )
            try:
                if await service.expire_offer(application_id):
                    await session.commit()
                    expired += 1
            except StaleDataError:
                await session.rollback()
    return expired


async def run_offer_expiry(
    session_factory: async_sessionmaker[AsyncSession],
    clock: Clock,
    stop: asyncio.Event,
    interval_seconds: float,
) -> None:
    while not stop.is_set():
        try:
            expired = await expire_offers(session_factory, clock)
            if expired:
                logger.info("Expired %s offers", expired)
        except Exception:
            logger.exception("Offer expiry run failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass
